import sys
import os

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

import database
import models
import import_service
from sqlalchemy.orm import Session

def reimport():
    # Init DB
    # Force drop and recreate tables to update schema
    print("Dropping and recreating tables...")
    models.Base.metadata.drop_all(bind=database.engine)
    models.Base.metadata.create_all(bind=database.engine)
    
    database.init_db()
    db = database.SessionLocal()
    
    # Create default user and account if they don't exist (since we dropped tables)
    if not db.query(models.User).first():
        user = models.User(email="demo@example.com", hashed_password="demo")
        db.add(user)
        db.commit()
        db.refresh(user)
        
        account = models.Account(name="Main Account", user_id=user.id)
        db.add(account)
        db.commit()
    
    file_path = "../broker-report-2025-12-01-2025-12-23.xlsx"
    print(f"Reading {file_path}...")
    
    with open(file_path, "rb") as f:
        content = f.read()
        
    try:
        print("Parsing file...")
        trades_data = import_service.parse_trade_file(content, file_path)
        print(f"Found {len(trades_data)} trades in file.")
        
        print("Saving to database...")
        count = 0
        for trade_dict in trades_data:
            # Add default account_id
            trade_dict["account_id"] = 1
            
            # Remove internal fields not in model
            if 'deal_sum' in trade_dict:
                del trade_dict['deal_sum']
            
            db_trade = models.Trade(**trade_dict)
            db.add(db_trade)
            count += 1
            
        db.commit()
        print(f"Successfully imported {count} trades.")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    reimport()
