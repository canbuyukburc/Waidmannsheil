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
from functools import wraps

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
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_system_admin = db.Column(db.Boolean, default=False)  # System admin flag
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
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
    role = db.Column(db.String(20), nullable=False)  # 'admin', 'envadm', 'maintainer', 'viewer'
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
    price_per_kg = db.Column(db.Float)  # Price per kg for bulk products
    price_per_package = db.Column(db.Float)  # Price per package for packaged products
    
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
        if self.is_packaged:
            return self.total_packages * self.price_per_package
        return self.total_weight_kg * self.price_per_kg
    
    @property
    def available_value(self):
        if self.is_packaged:
            return self.available_packages * self.price_per_package
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
    price_per_kg = db.Column(db.Float)  # Price per kg at time of sale (for bulk items)
    price_per_package = db.Column(db.Float)  # Price per package at time of sale (for packaged items)
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

# Make helper functions available in templates
@app.context_processor
def utility_processor():
    return dict(get_current_environment=get_current_environment)

def require_role(min_role):
    """Decorator to require minimum role in current environment"""
    env_role_hierarchy = {'viewer': 1, 'maintainer': 2, 'envadm': 3}
    
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # System admin check for admin-only routes
            if min_role == 'admin':
                if not current_user.is_system_admin:
                    flash('Access denied. System administrator role required.', 'error')
                    return redirect(url_for('dashboard'))
                return f(*args, **kwargs)
            
            # Environment role check
            env = get_current_environment()
            if not env:
                flash('No environment selected', 'error')
                return redirect(url_for('select_environment'))
            
            user_role = current_user.get_role_in_environment(env.id)
            if not user_role or env_role_hierarchy.get(user_role, 0) < env_role_hierarchy.get(min_role, 99):
                flash(f'Access denied. {min_role.title()} role required.', 'error')
                return redirect(url_for('dashboard'))
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Routes
@app.route('/')
@login_required
def dashboard():
    # System admin sees admin dashboard directly
    if current_user.is_system_admin:
        return redirect(url_for('admin_dashboard'))
    
    # Regular users see environment dashboard
    env = get_current_environment()
    if not env:
        return redirect(url_for('select_environment'))
    
    user_role = current_user.get_role_in_environment(env.id)
    if not user_role:
        flash('No access to this environment', 'error')
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
    
    return render_template('dashboard.html', 
                         products=products, 
                         stats=stats, 
                         environment=env,
                         user_role=user_role)

@app.route('/admin_dashboard')
@login_required  
@require_role('admin')
def admin_dashboard():
    # Get all environments and their users
    environments = Environment.query.all()
    env_data = []
    
    for env in environments:
        # Get users in environment
        user_envs = db.session.query(UserEnvironment, User).join(
            User, UserEnvironment.user_id == User.id
        ).filter(UserEnvironment.environment_id == env.id).all()
        
        env_data.append({
            'environment': env,
            'users': [(ue.role, user.username, user.email) for ue, user in user_envs],
            'user_count': len(user_envs)
        })
    
    return render_template('admin_dashboard.html', environments=env_data)
    
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
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            
            # System admin goes to admin dashboard
            if user.is_system_admin:
                return redirect(url_for('dashboard'))
            
            # Check if user has any environments
            user_envs = UserEnvironment.query.filter_by(user_id=user.id).all()
            if user_envs:
                # Set first environment as current
                session['current_environment_id'] = user_envs[0].environment_id
                return redirect(url_for('dashboard'))
            else:
                return redirect(url_for('select_environment'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """Public user registration with invite code"""
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        invite_code = request.form.get('invite_code', '').strip().upper()
        
        # Validate input
        if not username or not password:
            flash('Username and password are required', 'error')
            return render_template('register.html', invite_code=invite_code)
        
        if password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('register.html', invite_code=invite_code)
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long', 'error')
            return render_template('register.html', invite_code=invite_code)
        
        # Check if username already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists', 'error')
            return render_template('register.html', invite_code=invite_code)
        
        # Check if email already exists (if provided)
        if email:
            existing_email = User.query.filter_by(email=email).first()
            if existing_email:
                flash('Email already exists', 'error')
                return render_template('register.html', invite_code=invite_code)
        
        # Validate invite code if provided
        environment = None
        if invite_code:
            environment = Environment.query.filter_by(invite_code=invite_code, is_active=True).first()
            if not environment:
                flash('Invalid or expired invite code', 'error')
                return render_template('register.html', invite_code=invite_code)
        
        # Create user
        user = User(username=username, email=email or None)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()  # To get user.id
        
        # Add user to environment if invite code was used
        if environment:
            user_env = UserEnvironment(
                user_id=user.id,
                environment_id=environment.id,
                role='viewer'  # Default role, can be changed by envadm
            )
            db.session.add(user_env)
        
        db.session.commit()
        
        # Log the user in
        login_user(user)
        
        if environment:
            session['current_environment_id'] = environment.id
            flash(f'Account created successfully! You have been added to "{environment.name}" as a viewer.', 'success')
        else:
            flash('Account created successfully! You can now join environments using invite codes.', 'success')
        
        return redirect(url_for('dashboard'))
    
    # GET request - show registration form
    invite_code = request.args.get('invite_code', '').strip().upper()
    environment_name = None
    
    if invite_code:
        environment = Environment.query.filter_by(invite_code=invite_code, is_active=True).first()
        if environment:
            environment_name = environment.name
        else:
            flash('Invalid or expired invite code', 'error')
            invite_code = ''
    
    return render_template('register.html', invite_code=invite_code, environment_name=environment_name)

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

@app.route('/create_environment', methods=['GET', 'POST'])
@login_required
def create_environment():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        
        if not name:
            flash('Environment name is required', 'error')
            return render_template('create_environment.html')
        
        # Create new environment
        env = Environment(
            name=name,
            description=description,
            admin_id=current_user.id
        )
        db.session.add(env)
        db.session.flush()  # To get the env.id
        
        # Add current user as environment admin (envadm)
        user_env = UserEnvironment(
            user_id=current_user.id,
            environment_id=env.id,
            role='envadm'  # Environment admin, not system admin
        )
        db.session.add(user_env)
        db.session.commit()
        
        # Set as current environment
        session['current_environment_id'] = env.id
        
        flash(f'Environment "{name}" created successfully!')
        return redirect(url_for('dashboard'))
    
    return render_template('create_environment.html')

@app.route('/join_environment', methods=['GET', 'POST'])
@login_required
def join_environment():
    if request.method == 'POST':
        invite_code = request.form.get('invite_code', '').strip().upper()
        
        if not invite_code:
            flash('Invite code is required', 'error')
            return render_template('join_environment.html')
        
        env = Environment.query.filter_by(invite_code=invite_code, is_active=True).first()
        if not env:
            flash('Invalid or expired invite code', 'error')
            return render_template('join_environment.html')
        
        # Check if user already has access
        existing = UserEnvironment.query.filter_by(
            user_id=current_user.id,
            environment_id=env.id
        ).first()
        
        if existing:
            session['current_environment_id'] = env.id
            flash(f'You already have access to "{env.name}"')
            return redirect(url_for('dashboard'))
        
        # Add user as viewer by default
        user_env = UserEnvironment(
            user_id=current_user.id,
            environment_id=env.id,
            role='viewer'
        )
        db.session.add(user_env)
        db.session.commit()
        
        session['current_environment_id'] = env.id
        
        flash(f'Successfully joined "{env.name}" as viewer')
        return redirect(url_for('dashboard'))
    
    return render_template('join_environment.html')

@app.route('/join/<invite_code>')
def join_with_code(invite_code):
    """Direct join link for QR codes and shared URLs"""
    if not current_user.is_authenticated:
        # Redirect to registration page with invite code
        return redirect(url_for('register', invite_code=invite_code.upper()))
    
    # Handle joining logic same as join_environment POST
    env = Environment.query.filter_by(invite_code=invite_code.upper(), is_active=True).first()
    if not env:
        flash('Invalid or expired invite code', 'error')
        return redirect(url_for('select_environment'))
    
    existing = UserEnvironment.query.filter_by(
        user_id=current_user.id,
        environment_id=env.id
    ).first()
    
    if existing:
        session['current_environment_id'] = env.id
        flash(f'You already have access to "{env.name}"')
    else:
        user_env = UserEnvironment(
            user_id=current_user.id,
            environment_id=env.id,
            role='viewer'
        )
        db.session.add(user_env)
        db.session.commit()
        
        session['current_environment_id'] = env.id
        flash(f'Successfully joined "{env.name}" as viewer')
    
    return redirect(url_for('dashboard'))

@app.route('/add_product', methods=['GET', 'POST'])
@login_required
@require_role('maintainer')
def add_product():
    env = get_current_environment()
    if not env:
        return redirect(url_for('select_environment'))
    
    if request.method == 'POST':
        # Determine if this is bulk or packaged
        is_packaged = request.form.get('is_packaged') == 'on'
        
        if is_packaged:
            # Packaged product
            total_packages = int(request.form.get('total_packages'))
            package_size_kg = float(request.form.get('package_size_kg'))
            total_weight = total_packages * package_size_kg
            
            product = Product(
                name=request.form.get('name'),
                type=request.form.get('type'),
                animal_type=request.form.get('animal_type'),
                total_weight_kg=total_weight,
                available_weight_kg=total_weight,
                price_per_package=float(request.form.get('price_per_package')),
                is_packaged=True,
                package_size_kg=package_size_kg,
                total_packages=total_packages,
                available_packages=total_packages,
                environment_id=env.id,
                hunter_id=current_user.id,
                notes=request.form.get('notes')
            )
        else:
            # Bulk product
            total_weight = float(request.form.get('total_weight_kg'))
            
            product = Product(
                name=request.form.get('name'),
                type=request.form.get('type'),
                animal_type=request.form.get('animal_type'),
                total_weight_kg=total_weight,
                available_weight_kg=total_weight,
                price_per_kg=float(request.form.get('price_per_kg')),
                is_packaged=False,
                environment_id=env.id,
                hunter_id=current_user.id,
                notes=request.form.get('notes')
            )
        
        db.session.add(product)
        db.session.commit()
        flash('Product added successfully!')
        return redirect(url_for('dashboard'))
    
    return render_template('add_product.html', environment=env)

@app.route('/sell_product/<int:product_id>', methods=['GET', 'POST'])
@login_required
@require_role('maintainer')
def sell_product(product_id):
    env = get_current_environment()
    product = Product.query.filter_by(id=product_id, environment_id=env.id).first_or_404()
    
    if request.method == 'POST':
        if product.is_packaged:
            packages_to_sell = int(request.form.get('packages_to_sell', 0))
            if packages_to_sell > product.available_packages:
                flash('Not enough packages available', 'error')
                return render_template('sell_product.html', product=product, environment=env)
            
            quantity_kg = packages_to_sell * product.package_size_kg
            total_price = packages_to_sell * product.price_per_package  # Use per-package pricing
            
            # Update product inventory
            product.available_packages -= packages_to_sell
            product.available_weight_kg -= quantity_kg
            
        else:
            quantity_kg = float(request.form.get('quantity_kg', 0))
            if quantity_kg > product.available_weight_kg:
                flash('Not enough weight available', 'error')
                return render_template('sell_product.html', product=product, environment=env)
            
            packages_to_sell = None
            total_price = quantity_kg * product.price_per_kg
            
            # Update product inventory
            product.available_weight_kg -= quantity_kg
        
        # Create sale record
        if product.is_packaged:
            sale = Sale(
                product_id=product.id,
                environment_id=env.id,
                quantity_kg=quantity_kg,
                packages_sold=packages_to_sell,
                price_per_package=product.price_per_package,
                total_price=total_price,
                customer_name=request.form.get('customer_name'),
                customer_phone=request.form.get('customer_phone'),
                customer_email=request.form.get('customer_email'),
                sold_by=current_user.id,
                notes=request.form.get('notes')
            )
        else:
            sale = Sale(
                product_id=product.id,
                environment_id=env.id,
                quantity_kg=quantity_kg,
                packages_sold=packages_to_sell,
                price_per_kg=product.price_per_kg,
                total_price=total_price,
                customer_name=request.form.get('customer_name'),
                customer_phone=request.form.get('customer_phone'),
                customer_email=request.form.get('customer_email'),
                sold_by=current_user.id,
                notes=request.form.get('notes')
            )
        
        db.session.add(sale)
        db.session.commit()
        
        flash(f'Sale recorded successfully! ${total_price:.2f}')
        return redirect(url_for('dashboard'))
    
    return render_template('sell_product.html', product=product, environment=env)

@app.route('/product/<int:product_id>')
@login_required
def product_detail(product_id):
    env = get_current_environment()
    product = Product.query.filter_by(id=product_id, environment_id=env.id).first_or_404()
    
    # Get sales history
    sales = Sale.query.filter_by(product_id=product_id).order_by(Sale.sale_date.desc()).all()
    
    user_role = current_user.get_role_in_environment(env.id)
    
    return render_template('product_detail.html', 
                         product=product, 
                         sales=sales,
                         environment=env,
                         user_role=user_role)

@app.route('/environment_settings')
@login_required
@require_role('envadm')
def environment_settings():
    env = get_current_environment()
    if not env:
        return redirect(url_for('select_environment'))
    
    # Get all users in environment
    user_envs = db.session.query(UserEnvironment, User).join(
        User, UserEnvironment.user_id == User.id
    ).filter(UserEnvironment.environment_id == env.id).all()
    
    return render_template('environment_settings.html', 
                         environment=env, 
                         user_environments=user_envs)

@app.route('/manage_roles', methods=['GET', 'POST'])
@login_required
@require_role('envadm')
def manage_roles():
    env = get_current_environment()
    if not env:
        return redirect(url_for('select_environment'))
    
    if request.method == 'POST':
        user_id = int(request.form.get('user_id'))
        new_role = request.form.get('new_role')
        
        # Validate role
        if new_role not in ['envadm', 'maintainer', 'viewer']:
            flash('Invalid role selected', 'error')
            return redirect(url_for('manage_roles'))
        
        # Get user environment record
        user_env = UserEnvironment.query.filter_by(
            user_id=user_id, 
            environment_id=env.id
        ).first()
        
        if not user_env:
            flash('User not found in environment', 'error')
            return redirect(url_for('manage_roles'))
        
        # Prevent last envadm from changing their own role
        if user_env.user_id == current_user.id and user_env.role == 'envadm':
            envadm_count = UserEnvironment.query.filter_by(
                environment_id=env.id, role='envadm'
            ).count()
            if envadm_count <= 1 and new_role != 'envadm':
                flash('Cannot remove the last environment admin', 'error')
                return redirect(url_for('manage_roles'))
        
        # Update role
        old_role = user_env.role
        user_env.role = new_role
        db.session.commit()
        
        flash(f'User role updated from {old_role} to {new_role}', 'success')
        return redirect(url_for('manage_roles'))
    
    # Get all users in environment
    user_envs = db.session.query(UserEnvironment, User).join(
        User, UserEnvironment.user_id == User.id
    ).filter(UserEnvironment.environment_id == env.id).all()
    
    return render_template('manage_roles.html', 
                         environment=env, 
                         user_environments=user_envs)

@app.route('/create_user', methods=['GET', 'POST'])
@login_required
@require_role('admin')  # Only system admin can create users
def create_user():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        environment_id = request.form.get('environment_id')
        role = request.form.get('role', 'viewer')  # Default to viewer
        
        # Validate input
        if not username or not password:
            flash('Username and password are required', 'error')
            return render_template('create_user.html')
        
        # Check if username already exists
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash('Username already exists', 'error')
            return render_template('create_user.html')
        
        # Check if email already exists (if provided)
        if email:
            existing_email = User.query.filter_by(email=email).first()
            if existing_email:
                flash('Email already exists', 'error')
                return render_template('create_user.html')
        
        # Create user
        user = User(username=username, email=email or None)
        user.set_password(password)
        db.session.add(user)
        db.session.flush()  # To get user.id
        
        # Add user to environment if specified
        if environment_id:
            environment = Environment.query.get(environment_id)
            if environment:
                # Validate role
                if role not in ['envadm', 'maintainer', 'viewer']:
                    role = 'viewer'
                
                user_env = UserEnvironment(
                    user_id=user.id,
                    environment_id=environment.id,
                    role=role
                )
                db.session.add(user_env)
        
        db.session.commit()
        flash(f'User "{username}" created successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    
    # Get all environments for assignment
    environments = Environment.query.all()
    return render_template('create_user.html', environments=environments)

@app.route('/user_profile', methods=['GET', 'POST'])
@login_required
def user_profile():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        # Validate current password
        if not check_password_hash(current_user.password_hash, current_password):
            flash('Current password is incorrect', 'error')
            return render_template('user_profile.html')
        
        # Validate new passwords match
        if new_password != confirm_password:
            flash('New passwords do not match', 'error')
            return render_template('user_profile.html')
        
        # Validate password length
        if len(new_password) < 6:
            flash('Password must be at least 6 characters long', 'error')
            return render_template('user_profile.html')
        
        # Update password
        current_user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        flash('Password updated successfully!', 'success')
        return redirect(url_for('user_profile'))
    
    return render_template('user_profile.html')

@app.route('/admin/manage_users')
@login_required
@require_role('admin')
def manage_users():
    users = User.query.all()
    return render_template('manage_users.html', users=users)

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
@login_required
@require_role('admin')
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    
    # Don't allow deleting system admin
    if user.is_system_admin:
        flash('Cannot delete system administrator', 'error')
        return redirect(url_for('manage_users'))
    
    # Don't allow admin to delete themselves
    if user.id == current_user.id:
        flash('Cannot delete your own account', 'error')
        return redirect(url_for('manage_users'))
    
    # Check if user is admin of any environments
    admin_environments = Environment.query.filter_by(admin_id=user.id).all()
    if admin_environments:
        env_names = [env.name for env in admin_environments]
        flash(f'Cannot delete user "{user.username}" - they are admin of environments: {", ".join(env_names)}. Transfer ownership first.', 'error')
        return redirect(url_for('manage_users'))
    
    # Check if user has made sales
    sales_count = Sale.query.filter_by(sold_by=user.id).count()
    if sales_count > 0:
        flash(f'Cannot delete user "{user.username}" - they have {sales_count} sales records. Sales history cannot be deleted.', 'error')
        return redirect(url_for('manage_users'))
    
    username = user.username
    
    try:
        # Delete user environment assignments first
        UserEnvironment.query.filter_by(user_id=user.id).delete()
        
        # Delete the user
        db.session.delete(user)
        db.session.commit()
        
        flash(f'User "{username}" deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting user: {str(e)}', 'error')
    
    return redirect(url_for('manage_users'))

@app.route('/admin/manage_environments')
@login_required
@require_role('admin')
def manage_environments():
    environments = Environment.query.all()
    return render_template('manage_environments.html', environments=environments)

@app.route('/admin/delete_environment/<int:env_id>', methods=['POST'])
@login_required
@require_role('admin')
def delete_environment(env_id):
    environment = Environment.query.get_or_404(env_id)
    
    env_name = environment.name
    
    # Delete all user environment assignments
    UserEnvironment.query.filter_by(environment_id=env_id).delete()
    
    # Delete all products in this environment
    Product.query.filter_by(environment_id=env_id).delete()
    
    # Delete all sales in this environment
    Sale.query.filter_by(environment_id=env_id).delete()
    
    # Delete the environment
    db.session.delete(environment)
    db.session.commit()
    
    flash(f'Environment "{env_name}" deleted successfully', 'success')
    return redirect(url_for('manage_environments'))

if __name__ == '__main__':
    # For development only - production uses gunicorn
    with app.app_context():
        db.create_all()
        # Create default admin user if not exists
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', email='admin@example.com')
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
    
    app.run(host='0.0.0.0', port=5000, debug=True)