import csv
import random
import os
from datetime import datetime, timedelta

def main():
    random.seed(123)
    os.makedirs('data/test_fixtures', exist_ok=True)

    # 1. Customer dataset
    cust_rows = []
    cities = ['New York', 'London', 'Tokyo', 'San Francisco', 'Berlin', 'Sydney']
    tiers = ['Bronze', 'Silver', 'Gold', 'Platinum']
    for i in range(1, 81):
        cust_rows.append({
            'customer_id': f'CUST-{1000+i}',
            'full_name': f'Customer {i}',
            'age': random.randint(18, 72),
            'city': random.choice(cities),
            'signup_date': (datetime(2023, 1, 1) + timedelta(days=random.randint(0, 1000))).strftime('%Y-%m-%d'),
            'loyalty_tier': random.choice(tiers),
            'churn_risk': round(random.random(), 3)
        })
    with open('data/sample_customers.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(cust_rows[0].keys()))
        w.writeheader()
        w.writerows(cust_rows)

    # 2. Employee dataset
    emp_rows = []
    deps = ['Engineering', 'Marketing', 'Sales', 'Product', 'HR', 'Finance']
    statuses = ['Active', 'On Leave', 'Contractor']
    for i in range(1, 75):
        emp_rows.append({
            'employee_id': f'EMP-{200+i}',
            'employee_name': f'Employee {i}',
            'department': random.choice(deps),
            'salary': random.randint(45000, 185000),
            'hire_date': (datetime(2021, 1, 1) + timedelta(days=random.randint(0, 1500))).strftime('%Y-%m-%d'),
            'performance_rating': random.choice([3, 4, 5, 2, 4, 5]),
            'status': random.choice(statuses)
        })
    with open('data/sample_employees.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(emp_rows[0].keys()))
        w.writeheader()
        w.writerows(emp_rows)

    # 3. Sensor readings
    sensor_rows = []
    for i in range(1, 101):
        sensor_rows.append({
            'sensor_id': f'SENSOR-{random.randint(1, 5):02d}',
            'timestamp': (datetime(2026, 10, 1) + timedelta(minutes=i*15)).strftime('%Y-%m-%d %H:%M:%S'),
            'temperature': round(random.uniform(18.5, 95.0), 2),
            'humidity': round(random.uniform(20.0, 85.0), 2),
            'pressure_psi': round(random.uniform(28.0, 34.0), 2),
            'machine_status': random.choice(['NORMAL', 'NORMAL', 'NORMAL', 'WARNING', 'CRITICAL'])
        })
    with open('data/sample_sensor_readings.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(sensor_rows[0].keys()))
        w.writeheader()
        w.writerows(sensor_rows)

    # 4. Empty CSV
    with open('data/test_fixtures/empty_file.csv', 'w', encoding='utf-8') as f:
        pass

    # 5. Malformed CSV
    with open('data/test_fixtures/malformed.csv', 'w', encoding='utf-8') as f:
        f.write('col_a,col_b\n1,2,3,extra\nnot_valid')

    print('Successfully generated sample_customers.csv, sample_employees.csv, sample_sensor_readings.csv, and test fixtures.')

if __name__ == '__main__':
    main()
