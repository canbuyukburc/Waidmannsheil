# Additional routes to be added to app.py

@app.route('/environment_settings')
@login_required
@require_role('admin')
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
                price_per_kg=float(request.form.get('price_per_kg')),
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
            total_price = quantity_kg * product.price_per_kg
            
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

@app.route('/sales_history')
@login_required
def sales_history():
    env = get_current_environment()
    if not env:
        return redirect(url_for('select_environment'))
    
    sales = Sale.query.filter_by(environment_id=env.id).order_by(Sale.sale_date.desc()).all()
    
    return render_template('sales_history.html', sales=sales, environment=env)

@app.route('/api/products')
@login_required
def api_products():
    env = get_current_environment()
    if not env:
        return jsonify({'error': 'No environment selected'}), 400
    
    products = Product.query.filter_by(environment_id=env.id).order_by(Product.created_at.desc()).all()
    return jsonify([
        {
            'id': p.id,
            'name': p.name,
            'type': p.type,
            'animal_type': p.animal_type,
            'total_weight_kg': p.total_weight_kg,
            'available_weight_kg': p.available_weight_kg,
            'price_per_kg': p.price_per_kg,
            'is_packaged': p.is_packaged,
            'total_packages': p.total_packages,
            'available_packages': p.available_packages,
            'status': p.status,
            'total_value': p.total_value,
            'available_value': p.available_value,
            'created_at': p.created_at.isoformat() if p.created_at else None
        }
        for p in products
    ])