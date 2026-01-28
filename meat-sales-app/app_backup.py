from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
import secrets
import qrcode
import io
import base64

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'your-secret-key-change-this')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://user:password@localhost/meatshop')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    environments = db.relationship('UserEnvironment', back_populates='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_role_in_environment(self, environment_id):
        user_env = UserEnvironment.query.filter_by(
            user_id=self.id, 
            environment_id=environment_id
        ).first()
        return user_env.role if user_env else None
    
    def has_access_to_environment(self, environment_id):
        return self.get_role_in_environment(environment_id) is not None

class Environment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    invite_code = db.Column(db.String(12), unique=True, nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    admin = db.relationship('User', backref=db.backref('owned_environments', lazy=True))
    users = db.relationship('UserEnvironment', back_populates='environment', lazy=True)
    products = db.relationship('Product', backref='environment', lazy=True)
    
    def __init__(self, **kwargs):
        super(Environment, self).__init__(**kwargs)
        if not self.invite_code:
            self.invite_code = self.generate_invite_code()
    
    def generate_invite_code(self):
        return secrets.token_urlsafe(8)[:8].upper()
    
    def get_qr_code(self):
        invite_url = f"http://localhost:5000/join/{self.invite_code}"
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(invite_url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        return base64.b64encode(buffer.getvalue()).decode()

class UserEnvironment(db.Model):
    __tablename__ = 'user_environment'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    environment_id = db.Column(db.Integer, db.ForeignKey('environment.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin', 'maintainer', 'viewer'
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', back_populates='environments')
    environment = db.relationship('Environment', back_populates='users')
    
    __table_args__ = (db.UniqueConstraint('user_id', 'environment_id'),)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(50), nullable=False)  # 'sausage', 'leg', 'back', etc.
    animal_type = db.Column(db.String(50), nullable=False)  # 'deer', 'wild_boar', etc.
    
    # Inventory tracking
    total_weight_kg = db.Column(db.Float, nullable=False)  # Original total weight
    available_weight_kg = db.Column(db.Float, nullable=False)  # Current available weight
    price_per_kg = db.Column(db.Float, nullable=False)
    
    # Packaging support
    is_packaged = db.Column(db.Boolean, default=False)
    package_size_kg = db.Column(db.Float)  # Size of each package if packaged
    total_packages = db.Column(db.Integer)  # Total number of packages
    available_packages = db.Column(db.Integer)  # Available packages
    
    # Environment and user
    environment_id = db.Column(db.Integer, db.ForeignKey('environment.id'), nullable=False)
    hunter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)
    
    # Relationships
    hunter = db.relationship('User', backref=db.backref('products', lazy=True))
    sales = db.relationship('Sale', backref='product', lazy=True)
    
    @property
    def total_value(self):
        return self.total_weight_kg * self.price_per_kg
    
    @property
    def available_value(self):
        return self.available_weight_kg * self.price_per_kg
    
    @property
    def is_available(self):
        if self.is_packaged:
            return self.available_packages > 0
        return self.available_weight_kg > 0
    
    @property
    def status(self):
        if not self.is_available:
            return 'sold_out'
        elif self.is_packaged:
            if self.available_packages == self.total_packages:
                return 'available'
            else:
                return 'partial'
        else:
            if self.available_weight_kg == self.total_weight_kg:
                return 'available'
            else:
                return 'partial'

class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    environment_id = db.Column(db.Integer, db.ForeignKey('environment.id'), nullable=False)
    
    # Sale details
    quantity_kg = db.Column(db.Float)  # Weight sold (for bulk items)
    packages_sold = db.Column(db.Integer)  # Packages sold (for packaged items)
    price_per_kg = db.Column(db.Float, nullable=False)  # Price at time of sale
    total_price = db.Column(db.Float, nullable=False)
    
    # Customer information
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(20))
    customer_email = db.Column(db.String(120))
    
    # Sale metadata
    sale_date = db.Column(db.DateTime, default=datetime.utcnow)
    sold_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    notes = db.Column(db.Text)
    
    # Relationships
    seller = db.relationship('User', backref=db.backref('sales', lazy=True))
    environment = db.relationship('Environment', backref=db.backref('sales', lazy=True))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Helper functions
def get_current_environment():
    """Get the currently selected environment from session"""
    env_id = session.get('current_environment_id')
    if env_id and current_user.is_authenticated:
        env = Environment.query.get(env_id)
        if env and current_user.has_access_to_environment(env_id):
            return env
    return None

def require_role(min_role):
    """Decorator to require minimum role in current environment"""
    role_hierarchy = {'viewer': 1, 'maintainer': 2, 'admin': 3}
    
    def decorator(f):
        def decorated_function(*args, **kwargs):
            env = get_current_environment()
            if not env:
                flash('No environment selected', 'error')
                return redirect(url_for('select_environment'))
            
            user_role = current_user.get_role_in_environment(env.id)
            if not user_role or role_hierarchy.get(user_role, 0) < role_hierarchy.get(min_role, 99):
                flash(f'Access denied. {min_role.title()} role required.', 'error')
                return redirect(url_for('dashboard'))
            
            return f(*args, **kwargs)
        decorated_function.__name__ = f.__name__
        return decorated_function
    return decorator

# Routes
@app.route('/')
@login_required
def dashboard():
    env = get_current_environment()
    if not env:
        return redirect(url_for('select_environment'))
    
    # Get products for current environment
    products = Product.query.filter_by(environment_id=env.id).order_by(Product.created_at.desc()).all()
    
    # Calculate statistics
    stats = {
        'total_products': len(products),
        'available_products': len([p for p in products if p.is_available]),
        'sold_out_products': len([p for p in products if not p.is_available]),
        'total_value': sum(p.total_value for p in products),
        'available_value': sum(p.available_value for p in products),
        'sold_value': sum(p.total_value - p.available_value for p in products)
    }
    
    user_role = current_user.get_role_in_environment(env.id)
    
    return render_template('dashboard.html', 
                         products=products, 
                         stats=stats, 
                         environment=env,
                         user_role=user_role)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        print(f"Login attempt - Username: {username}, Password provided: {'Yes' if password else 'No'}")
        
        user = User.query.filter_by(username=username).first()
        
        if user:
            print(f"User found: {user.username}")
            if user.check_password(password):
                print("Password correct - logging in user")
                login_user(user)
                print("User logged in successfully")
                
                # Check if user has any environments
                user_envs = UserEnvironment.query.filter_by(user_id=user.id).all()
                if user_envs:
                    # Set first environment as current
                    session['current_environment_id'] = user_envs[0].environment_id
                    return redirect(url_for('dashboard'))
                else:
                    return redirect(url_for('select_environment'))
            else:
                print("Password incorrect")
                flash('Invalid username or password', 'error')
        else:
            print("User not found")
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    session.pop('current_environment_id', None)
    logout_user()
    return redirect(url_for('login'))

@app.route('/select_environment')
@login_required
def select_environment():
    # Get user's environments
    user_envs = db.session.query(UserEnvironment, Environment).join(
        Environment, UserEnvironment.environment_id == Environment.id
    ).filter(UserEnvironment.user_id == current_user.id).all()
    
    environments = [(ue, env) for ue, env in user_envs]
    
    return render_template('select_environment.html', environments=environments)

@app.route('/switch_environment/<int:environment_id>')
@login_required
def switch_environment(environment_id):
    if current_user.has_access_to_environment(environment_id):
        session['current_environment_id'] = environment_id
        flash('Environment switched successfully')
    else:
        flash('Access denied to this environment', 'error')
    return redirect(url_for('dashboard'))

@app.route('/add_product', methods=['GET', 'POST'])
@login_required
def add_product():
    if request.method == 'POST':
        product = Product(
            name=request.form.get('name'),
            type=request.form.get('type'),
            animal_type=request.form.get('animal_type'),
            weight_kg=float(request.form.get('weight_kg')),
            price_per_kg=float(request.form.get('price_per_kg')),
            total_price=float(request.form.get('weight_kg')) * float(request.form.get('price_per_kg')),
            hunter_id=current_user.id,
            notes=request.form.get('notes')
        )
        db.session.add(product)
        db.session.commit()
        flash('Product added successfully!')
        return redirect(url_for('dashboard'))
    
    return render_template('add_product.html')

@app.route('/update_status/<int:product_id>', methods=['POST'])
@login_required
def update_status(product_id):
    product = Product.query.get_or_404(product_id)
    new_status = request.form.get('status')
    
    product.status = new_status
    
    if new_status == 'reserved':
        product.reserved_at = datetime.utcnow()
        product.customer_name = request.form.get('customer_name')
        product.customer_phone = request.form.get('customer_phone')
    elif new_status == 'sold':
        product.sold_at = datetime.utcnow()
        product.customer_name = request.form.get('customer_name')
        product.customer_phone = request.form.get('customer_phone')
    elif new_status == 'available':
        product.reserved_at = None
        product.sold_at = None
        product.customer_name = None
        product.customer_phone = None
    
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/product/<int:product_id>')
@login_required
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template('product_detail.html', product=product)

@app.route('/api/products')
@login_required
def api_products():
    products = Product.query.order_by(Product.created_at.desc()).all()
    return jsonify([
        {
            'id': p.id,
            'name': p.name,
            'type': p.type,
            'animal_type': p.animal_type,
            'weight_kg': p.weight_kg,
            'total_price': p.total_price,
            'status': p.status,
            'customer_name': p.customer_name,
            'created_at': p.created_at.isoformat() if p.created_at else None
        }
        for p in products
    ])

if __name__ == '__main__':
    # For development only - production uses gunicorn
    with app.app_context():
        db.create_all()
        # Create default admin user if not exists
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', email='admin@example.com', role='admin')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
    
    app.run(host='0.0.0.0', port=5000, debug=True)