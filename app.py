
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text
from datetime import datetime, timedelta
from functools import wraps
import uuid

app = Flask(__name__)
app.secret_key = 'unity_arena_ultra_erp_v8'

# PostgreSQL Connection
DB_URL = 'postgresql://InventoryManagement_puttingarm:UnityShuttleArena%40123@5zvxg5.h.filess.io:5434/InventoryManagement_puttingarm'
app.config['SQLALCHEMY_DATABASE_URI'] = DB_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Models ---
class Product(db.Model):
    __table_args__ = {'schema': 'unity1'}
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    category = db.Column(db.String(50)) 
    buy_price = db.Column(db.Float, default=0.0)
    sell_price = db.Column(db.Float, nullable=False)
    stock = db.Column(db.Integer, default=0)
    low_stock_limit = db.Column(db.Integer, default=5)

class Transaction(db.Model):
    __table_args__ = {'schema': 'unity1'}
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.String(50))
    item_name = db.Column(db.String(100))
    category = db.Column(db.String(50)) 
    qty = db.Column(db.Integer)
    total_sell = db.Column(db.Float)
    total_cost = db.Column(db.Float)
    description = db.Column(db.Text) 
    timestamp = db.Column(db.DateTime, default=datetime.now)

class Expense(db.Model):
    __table_args__ = {'schema': 'unity1'}
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    amount = db.Column(db.Float)
    category = db.Column(db.String(50)) 
    timestamp = db.Column(db.DateTime, default=datetime.now)

class StockHistory(db.Model):
    __table_args__ = {'schema': 'unity1'}
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(100))
    added_qty = db.Column(db.Integer)
    timestamp = db.Column(db.DateTime, default=datetime.now)

# --- DB Migration & Initialization ---
with app.app_context():
    db.session.execute(text("CREATE SCHEMA IF NOT EXISTS unity1;"))
    db.create_all()
    try:
        db.session.execute(text("ALTER TABLE unity1.transaction ADD COLUMN IF NOT EXISTS description TEXT;"))
        db.session.commit()
    except: pass

# --- Auth ---
def login_required(role_needed=None):
    def wrapper(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user' not in session: return redirect(url_for('login'))
            if role_needed == 'owner' and session.get('role') != 'owner': return "Unauthorized", 403
            return f(*args, **kwargs)
        return decorated
    return wrapper

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u, p = request.form.get('user'), request.form.get('pass')
        if u == 'owner' and p == 'owner123':
            session['user'], session['role'] = 'Owner', 'owner'
            return redirect(url_for('index'))
        if u == 'manager' and p == 'manager123':
            session['user'], session['role'] = 'Manager', 'manager'
            return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required()
def index():
    prods = Product.query.order_by(Product.name).all()
    today_txns = Transaction.query.filter(db.func.date(Transaction.timestamp) == datetime.now().date()).order_by(Transaction.timestamp.desc()).all()
    slots = ["6 AM", "7 AM", "8 AM", "9 AM", "10 AM", "11 AM", "12 PM", "1 PM", "2 PM", "3 PM", "4 PM", "5 PM", "6 PM", "7 PM", "8 PM", "9 PM", "10 PM", "11 PM", "12 AM", "1 AM"]
    low_stock_items = Product.query.filter(Product.stock <= Product.low_stock_limit).all()
    return render_template('index.html', products=prods, slots=slots, today_txns=today_txns, low_stock=low_stock_items)

@app.route('/submit_order', methods=['POST'])
@login_required()
def submit_order():
    data = request.json
    order_id = str(uuid.uuid4())[:8]
    for item in data['items']:
        p = Product.query.filter_by(name=item['name']).first()
        cost = p.buy_price * item['qty'] if (p and p.category == 'Sale') else 0
        if p and p.category == 'Sale': p.stock -= item['qty']
        txn = Transaction(order_id=order_id, item_name=item['name'], category=item['category'], 
                          qty=item['qty'], total_sell=item['price'] * item['qty'], total_cost=cost,
                          description=data.get('desc'))
        db.session.add(txn)
    db.session.commit()
    return jsonify({"success": True})

@app.route('/undo_txn/<int:id>', methods=['POST'])
@login_required()
def undo_txn(id):
    t = Transaction.query.get(id)
    if t:
        p = Product.query.filter_by(name=t.item_name).first()
        if p and t.category == 'Sale': p.stock += t.qty
        db.session.delete(t)
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/admin')
@login_required('owner')
def admin():
    cat_filter = request.args.get('category', 'All')
    start_date = request.args.get('start', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    end_date = request.args.get('end', datetime.now().strftime('%Y-%m-%d'))
    
    # Financial Logic
    q_txns = Transaction.query.filter(db.func.date(Transaction.timestamp) >= start_date, db.func.date(Transaction.timestamp) <= end_date)
    if cat_filter != 'All' and cat_filter != 'Expense': q_txns = q_txns.filter_by(category=cat_filter)
    txns = q_txns.all()

    q_exp = Expense.query.filter(db.func.date(Expense.timestamp) >= start_date, db.func.date(Expense.timestamp) <= end_date)
    if cat_filter == 'Expense': q_exp = q_exp.filter_by(category=cat_filter)
    expenses = q_exp.all()

    products = Product.query.all()
    stock_hist = StockHistory.query.order_by(StockHistory.timestamp.desc()).limit(10).all()

    rev = sum(t.total_sell for t in txns)
    cogs = sum(t.total_cost for t in txns)
    total_exp = sum(e.amount for e in expenses)
    net_profit = rev - (cogs + total_exp)
    
    # Chart Data Preparation
    chart_data = {'Sale': 0, 'Rent': 0, 'Booking': 0}
    for t in txns: chart_data[t.category] = chart_data.get(t.category, 0) + t.total_sell

    return render_template('admin.html', revenue=rev, expenses_total=total_exp, profit=net_profit, 
                           products=products, stock_history=stock_hist, expenses=expenses,
                           start_date=start_date, end_date=end_date, cat_filter=cat_filter, 
                           chart_data=chart_data, txns=txns)

@app.route('/product/add', methods=['POST'])
@login_required('owner')
def add_product():
    name = request.form.get('name')
    qty = int(request.form.get('stock') or 0)
    buy = float(request.form.get('buy') or 0)
    sell = float(request.form.get('sell') or 0)
    low = int(request.form.get('low_limit') or 5)
    
    p = Product.query.filter_by(name=name).first()
    if p:
        p.stock += qty
        p.buy_price, p.sell_price, p.low_stock_limit = buy, sell, low
    else:
        p = Product(name=name, category=request.form.get('cat'), buy_price=buy, sell_price=sell, stock=qty, low_stock_limit=low)
        db.session.add(p)
    db.session.add(StockHistory(product_name=name, added_qty=qty))
    db.session.commit()
    return redirect(url_for('admin'))

@app.route('/add_expense', methods=['POST'])
@login_required('owner')
def add_expense():
    e = Expense(title=request.form['title'], amount=float(request.form['amount']), category=request.form['cat'])
    db.session.add(e)
    db.session.commit()
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(debug=True)
