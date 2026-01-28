# Meat Sales Management System

A web application designed for hunters and their families to manage meat product sales, track inventory status (available, reserved, sold), and coordinate between hunters and sellers.

## Features

- **Product Management**: Add and track meat products with details like type, weight, price
- **Status Tracking**: Monitor if products are available, reserved, or sold
- **Customer Information**: Store customer details for reserved/sold items
- **Mobile Responsive**: Works well on smartphones and tablets
- **User Authentication**: Secure login system
- **Dashboard**: Overview of all products with statistics
- **PostgreSQL Database**: Reliable data storage

## Quick Start with Docker

1. **Clone and navigate to the project**:
   ```bash
   cd meat-sales-app
   ```

2. **Start the application**:
   ```bash
   docker-compose up -d
   ```

3. **Access the application**:
   - Open your browser and go to `http://localhost:5000`
   - Login with default credentials: `admin` / `admin123`

4. **Stop the application**:
   ```bash
   docker-compose down
   ```

## Manual Setup (Development)

### Prerequisites
- Python 3.11+
- PostgreSQL
- pip

### Installation

1. **Create a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env file with your database credentials
   ```

4. **Set up PostgreSQL database**:
   ```sql
   CREATE DATABASE meatshop;
   CREATE USER meatshop WITH PASSWORD 'password123';
   GRANT ALL PRIVILEGES ON DATABASE meatshop TO meatshop;
   ```

5. **Run the application**:
   ```bash
   python app.py
   ```

## Usage

### For Hunters:
1. Add new meat products with details (type, weight, price)
2. Upload photos of products
3. View all products and their current status

### For Sellers (Wife):
1. Update product status (available → reserved → sold)
2. Add customer information when reserving/selling
3. Track customer contact details
4. Monitor inventory and sales statistics

### Product Types Supported:
- Sausages
- Leg cuts
- Back cuts
- Shoulder cuts
- Ribs
- Ground meat
- Steaks
- Roasts
- Custom types

### Animal Types Supported:
- Deer
- Wild Boar
- Elk
- Moose
- Rabbit
- Duck
- Pheasant
- Wild Turkey
- Custom types

## API Endpoints

- `GET /api/products` - Get all products in JSON format
- `POST /update_status/<product_id>` - Update product status
- `POST /add_product` - Add new product

## Database Schema

### Users Table
- `id` (Primary Key)
- `username` (Unique)
- `email` (Unique)
- `password_hash`
- `role` (admin, hunter, seller)
- `created_at`

### Products Table
- `id` (Primary Key)
- `name`
- `type` (sausage, leg, back, etc.)
- `animal_type` (deer, wild_boar, etc.)
- `weight_kg`
- `price_per_kg`
- `total_price`
- `status` (available, reserved, sold)
- `hunter_id` (Foreign Key to Users)
- `customer_name`
- `customer_phone`
- `notes`
- `created_at`
- `reserved_at`
- `sold_at`

## Configuration

### Environment Variables
- `DATABASE_URL`: PostgreSQL connection string
- `SECRET_KEY`: Flask secret key for sessions
- `FLASK_ENV`: development/production
- `FLASK_DEBUG`: True/False

### Docker Configuration
The application is configured to run with:
- Flask app on port 5000
- PostgreSQL on port 5432
- Persistent data storage

## Mobile Optimization

The application is designed to work well on mobile devices:
- Responsive Bootstrap 5 design
- Touch-friendly buttons
- Optimized tables for small screens
- Easy-to-use forms

## Security Features

- Password hashing with Werkzeug
- Session-based authentication
- Login required for all operations
- CSRF protection (built into Flask-Login)

## Production Deployment

1. **Update environment variables** in docker-compose.yml:
   - Change default passwords
   - Set a strong SECRET_KEY
   - Configure proper database credentials

2. **Use a reverse proxy** (nginx) for SSL/HTTPS

3. **Set up regular backups** for PostgreSQL data

4. **Monitor logs** and set up log rotation

## Troubleshooting

### Common Issues

1. **Database connection issues**:
   - Check PostgreSQL is running
   - Verify DATABASE_URL is correct
   - Ensure database and user exist

2. **Permission denied errors**:
   - Check file permissions
   - Ensure Docker has proper permissions

3. **Port conflicts**:
   - Change ports in docker-compose.yml if 5000 or 5432 are in use

### Logs
View application logs:
```bash
docker-compose logs web
```

View database logs:
```bash
docker-compose logs db
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is open source and available under the MIT License.