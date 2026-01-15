from flask import Flask, jsonify, request
from flask_cors import CORS
import pymysql

app = Flask(__name__)
# 允许跨域
CORS(app, resources={r"/*": {"origins": "*"}})

# 数据库配置
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'your_password', # ⚠️ 记得改成你的 MySQL 密码
    'database': 'scenic_area_db', # ⚠️ 确认你的数据库名
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

def get_db_connection():
    return pymysql.connect(**db_config)

# ================= 登录接口 (适配新表结构) =================
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    account = data.get('id')  # 前端传来的账号/ID
    password = data.get('password')
    role = data.get('role')   # user / merchant / admin
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            user = None
            result = {}

            if role == 'user':
                # 游客登录：匹配 phone 或 tourist_id
                # 注意：这里我们用新加的 password 字段
                sql = "SELECT * FROM Tourist WHERE (phone = %s OR tourist_id = %s)"
                cursor.execute(sql, (account, account))
                user = cursor.fetchone()
                if user and str(user.get('password')) == password: # 简单比对
                    result = {
                        'success': True,
                        'role': 'user',
                        'id': user['tourist_id'],
                        'name': user['name']
                    }

            elif role == 'merchant':
                # 商铺登录：匹配 account
                sql = "SELECT * FROM Shop WHERE account = %s"
                cursor.execute(sql, (account,))
                user = cursor.fetchone()
                if user and str(user.get('password')) == password:
                    result = {
                        'success': True,
                        'role': 'merchant',
                        'id': user['shop_id'],
                        'name': user['shop_name']
                    }

            elif role == 'admin':
                # 管理员 (假设你之前建了 Admin 表，如果没有，这里需要单独处理)
                # 这里暂时写死一个 admin 用于测试，如果你的 SQL 里没有 Admin 表
                if account == 'admin' and password == '123456':
                    result = { 'success': True, 'role': 'admin', 'id': 0, 'name': '管理员' }

            if result:
                return jsonify(result)
            else:
                return jsonify({'success': False, 'message': '账号或密码错误'}), 401
    finally:
        conn.close()

# ================= 游客接口 =================

# 1. 获取商品/门票列表
@app.route('/api/products', methods=['GET'])
def get_products():
    shop_id = request.args.get('shop_id') # 可选参数
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 如果传了 shop_id，查 ShopProduct 关联的商品
            if shop_id:
                sql = """
                SELECT p.* FROM Product p
                JOIN ShopProduct sp ON p.product_id = sp.product_id
                WHERE sp.shop_id = %s
                """
                cursor.execute(sql, (shop_id,))
            else:
                # 否则查所有
                sql = "SELECT * FROM Product"
                cursor.execute(sql)
            
            products = cursor.fetchall()
            return jsonify({'success': True, 'data': products})
    finally:
        conn.close()

# 2. 下单接口 (适配 Order 和 OrderInfo)
@app.route('/api/order', methods=['POST'])
def create_order():
    data = request.json
    uid = data.get('tourist_id')
    pid = data.get('product_id')
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 1. 查价格
            cursor.execute("SELECT unit_price FROM Product WHERE product_id = %s", (pid,))
            prod = cursor.fetchone()
            if not prod:
                return jsonify({'success': False, 'message': '商品不存在'}), 404
            
            price = prod['unit_price']
            
            # 2. 创建主订单 (Order 表)
            # 生成简单的 order_id (实际应用应用 UUID)
            import time
            order_id = int(time.time()) 
            
            sql_order = """
                INSERT INTO `Order` (order_id, tourist_id, total_price, order_time, order_status, comment)
                VALUES (%s, %s, %s, NOW(), '已支付', 'APP下单')
            """
            cursor.execute(sql_order, (order_id, uid, price))
            
            # 3. 创建订单明细 (OrderInfo 表)
            # 注意列名：quantity, unit_price, discount, coupon_type
            sql_info = """
                INSERT INTO OrderInfo (order_id, product_id, quantity, unit_price, discount, comment)
                VALUES (%s, %s, 1, %s, 1.0, '无优惠')
            """
            cursor.execute(sql_info, (order_id, pid, price))
            
            # 4. 扣库存 (Product 表)
            cursor.execute("UPDATE Product SET remaining_stock = remaining_stock - 1 WHERE product_id = %s", (pid,))
            
        conn.commit()
        return jsonify({'success': True, 'message': '下单成功'})
    except Exception as e:
        conn.rollback()
        print(e)
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

# 3. 查订单 (适配 OrderInfo)
@app.route('/api/orders/<int:uid>', methods=['GET'])
def get_orders(uid):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 关联 Order 和 OrderInfo 和 Product
            sql = """
                SELECT 
                    o.order_id, 
                    o.order_time, 
                    p.product_name, 
                    oi.quantity, 
                    oi.unit_price as price
                FROM `Order` o
                JOIN OrderInfo oi ON o.order_id = oi.order_id
                JOIN Product p ON oi.product_id = p.product_id
                WHERE o.tourist_id = %s
                ORDER BY o.order_time DESC
            """
            cursor.execute(sql, (uid,))
            orders = cursor.fetchall()
            return jsonify({'success': True, 'data': orders})
    finally:
        conn.close()

# 4. 个人信息 (适配 Tourist 表)
@app.route('/api/user/profile/<int:uid>', methods=['GET'])
def get_profile(uid):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = "SELECT * FROM Tourist WHERE tourist_id = %s"
            cursor.execute(sql, (uid,))
            user = cursor.fetchone()
            if user:
                return jsonify({
                    'success': True,
                    'data': {
                        'name': user['name'],
                        'phone': user['phone'],
                        'level': user['member_level'],
                        'spending': float(user['total_spending'] or 0)
                    }
                })
            return jsonify({'success': False}), 404
    finally:
        conn.close()

# ================= 商铺接口 =================

# 商铺营收 (适配 ShopRevenue 表)
@app.route('/api/merchant/revenue/<int:sid>', methods=['GET'])
def get_shop_revenue(sid):
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 查 ShopRevenue 表
            sql = "SELECT report_month, revenue FROM ShopRevenue WHERE shop_id = %s"
            cursor.execute(sql, (sid,))
            revenue_list = cursor.fetchall()
            
            # 计算总和
            total = sum(item['revenue'] for item in revenue_list) if revenue_list else 0
            
            # 这里简化处理，不返回 details 细节，因为结构变了
            return jsonify({
                'success': True,
                'overview': { 'total_income': float(total), 'total_count': len(revenue_list) },
                'details': [] # 暂时留空
            })
    finally:
        conn.close()

# 商铺录入营收 (适配 ShopRevenue)
@app.route('/api/merchant/revenue/add', methods=['POST'])
def add_revenue():
    data = request.json
    sid = data.get('merchant_id')
    month = data.get('month') # '2026-01'
    amount = data.get('amount')
    remarks = data.get('remarks')
    
    # 构造日期 '2026-01-01' 因为你的 CHECK 约束 EXTRACT(DAY FROM report_month) == 1
    report_date = f"{month}-01"

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            sql = """
                INSERT INTO ShopRevenue (shop_id, report_month, revenue, comment)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE revenue = %s, comment = %s
            """
            cursor.execute(sql, (sid, report_date, amount, remarks, amount, remarks))
        conn.commit()
        return jsonify({'success': True, 'message': '录入成功'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)})
    finally:
        conn.close()

# 注册 (游客)
@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    phone = data.get('phone')
    password = data.get('password')
    name = data.get('name', '新用户')
    
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 生成 ID
            import random
            new_id = random.randint(1000, 9999)
            
            sql = """
                INSERT INTO Tourist (tourist_id, name, phone, member_level, password, total_spending)
                VALUES (%s, %s, %s, 0, %s, 0)
            """
            cursor.execute(sql, (new_id, name, phone, password))
        conn.commit()
        return jsonify({'success': True, 'message': '注册成功'})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(debug=True)