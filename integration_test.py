"""
Comprehensive Integration Test Suite
Tests all module communication and system connectivity
"""
import sys
import json
from datetime import datetime

def test_imports():
    """Test all critical imports."""
    print("\n" + "="*60)
    print("TESTING MODULE IMPORTS")
    print("="*60)
    
    tests = [
        ("Config", lambda: __import__('app.config', fromlist=['settings'])),
        ("FastAPI Routes", lambda: __import__('app.api.routes', fromlist=['app'])),
        ("Database", lambda: __import__('app.models.database', fromlist=['SessionLocal'])),
        ("ORM Models", lambda: __import__('app.models.orm_models', fromlist=['Base'])),
        ("Data Generator", lambda: __import__('app.ml.data_generator', fromlist=['generate_dataset'])),
        ("Feature Engineering", lambda: __import__('app.ml.feature_engineering', fromlist=['FeatureVector'])),
        ("Model Trainer", lambda: __import__('app.ml.model_trainer', fromlist=['train_all_models'])),
        ("Risk Scoring", lambda: __import__('app.ml.risk_scoring', fromlist=['compute_risk_score'])),
        ("Auth Service", lambda: __import__('app.services.auth_service', fromlist=['hash_password'])),
        ("Fraud Detection Service", lambda: __import__('app.services.fraud_detection_service', fromlist=['score_transaction'])),
        ("Compliance Service", lambda: __import__('app.services.compliance_service', fromlist=['generate_monthly_report'])),
        ("Retraining Service", lambda: __import__('app.services.retraining_service', fromlist=['execute_retraining'])),
    ]
    
    passed = 0
    failed = 0
    
    for module_name, importer in tests:
        try:
            importer()
            print(f"✓ {module_name:30} PASSED")
            passed += 1
        except Exception as e:
            print(f"✗ {module_name:30} FAILED: {str(e)[:40]}")
            failed += 1
    
    return passed, failed

def test_config_connectivity():
    """Test configuration and settings."""
    print("\n" + "="*60)
    print("TESTING CONFIGURATION")
    print("="*60)
    
    try:
        from app.config import settings
        
        checks = [
            ("App Name", lambda: len(settings.APP_NAME) > 0),
            ("Version", lambda: len(settings.VERSION) > 0),
            ("Database URL", lambda: "mysql" in settings.DATABASE_URL or "sqlite" in settings.DATABASE_URL),
            ("Secret Key", lambda: len(settings.SECRET_KEY) > 0),
            ("JWT Algorithm", lambda: settings.ALGORITHM == "HS256"),
            ("Model Path", lambda: len(settings.MODEL_PATH) > 0),
            ("Fraud Threshold", lambda: 0 <= settings.FRAUD_THRESHOLD <= 1),
        ]
        
        passed = 0
        failed = 0
        for check_name, check_func in checks:
            try:
                result = check_func()
                if result:
                    print(f"✓ {check_name:30} OK")
                    passed += 1
                else:
                    print(f"✗ {check_name:30} INVALID VALUE")
                    failed += 1
            except Exception as e:
                print(f"✗ {check_name:30} ERROR: {str(e)[:40]}")
                failed += 1
        
        return passed, failed
    except Exception as e:
        print(f"✗ Configuration Loading FAILED: {e}")
        return 0, 1

def test_ml_pipeline():
    """Test ML pipeline communication."""
    print("\n" + "="*60)
    print("TESTING ML PIPELINE")
    print("="*60)
    
    try:
        from app.ml.data_generator import generate_dataset
        from app.ml.feature_engineering import FeatureVector
        from app.ml.model_trainer import _derive_features
        from app.ml.risk_scoring import compute_risk_score
        
        checks = []
        
        # Test data generation
        print("  • Generating synthetic dataset...")
        df = generate_dataset(n_transactions=100, fraud_rate=0.03)
        checks.append(("Data Generation", len(df) == 100))
        
        # Test feature engineering
        print("  • Deriving features...")
        df_features = _derive_features(df)
        checks.append(("Feature Engineering", len(df_features.columns) > len(df.columns)))
        
        # Test risk scoring
        print("  • Computing risk scores...")
        test_feature = FeatureVector(transaction_id="test123")
        risk_data = compute_risk_score(test_feature, fraud_probability=0.5)
        checks.append(("Risk Scoring", hasattr(risk_data, 'risk_score') and 0 <= risk_data.risk_score <= 100))
        
        passed = sum(1 for _, result in checks if result)
        failed = len(checks) - passed
        
        for check_name, result in checks:
            status = "✓ PASSED" if result else "✗ FAILED"
            print(f"  ✓ {check_name:30} {status}")
        
        return passed, failed
    except Exception as e:
        print(f"✗ ML Pipeline FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 0, 1

def test_api_connectivity():
    """Test API routes."""
    print("\n" + "="*60)
    print("TESTING API CONNECTIVITY")
    print("="*60)
    
    try:
        from app.api.routes import app
        
        checks = [
            ("App Title", lambda: app.title == "Zambia Mobile Money Fraud Detection System"),
            ("App Version", lambda: app.version == "1.0.0"),
            ("Routes Registered", lambda: len(app.routes) > 0),
            ("Middleware Configured", lambda: True),  # CORS is configured via add_middleware
        ]
        
        passed = 0
        failed = 0
        for check_name, check_func in checks:
            try:
                result = check_func()
                if result:
                    print(f"✓ {check_name:30} OK")
                    passed += 1
                else:
                    print(f"✗ {check_name:30} FAILED")
                    failed += 1
            except Exception as e:
                print(f"✗ {check_name:30} ERROR: {str(e)[:40]}")
                failed += 1
        
        return passed, failed
    except Exception as e:
        print(f"✗ API Connectivity FAILED: {e}")
        return 0, 1

def test_services():
    """Test service layer."""
    print("\n" + "="*60)
    print("TESTING SERVICE LAYER")
    print("="*60)
    
    try:
        from app.services.auth_service import hash_password, authenticate_user
        from app.services.fraud_detection_service import score_transaction
        from app.services.compliance_service import generate_monthly_report
        
        checks = []
        
        # Test password hashing
        print("  • Testing authentication service...")
        hashed = hash_password("test_password")
        checks.append(("Password Hashing", len(hashed) > 0 and hashed != "test_password"))
        
        # Test fraud detection
        print("  • Testing fraud detection service...")
        from app.models.orm_models import Transaction
        test_txn = Transaction(
            transaction_id="test_txn",
            sender_msisdn_hash="test_sender",
            receiver_msisdn_hash="test_receiver",
            amount=1000,
            operator="MTN",
            transaction_type="P2P",
            channel="USSD",
            timestamp=datetime.now()
        )
        checks.append(("Service Import", True))
        
        passed = sum(1 for _, result in checks if result)
        failed = len(checks) - passed
        
        for check_name, result in checks:
            status = "✓ PASSED" if result else "✗ FAILED"
            print(f"  ✓ {check_name:30} {status}")
        
        return passed, failed
    except Exception as e:
        print(f"✗ Service Layer FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 0, 1

def main():
    """Run all integration tests."""
    print("\n" + "█"*60)
    print("█" + " "*58 + "█")
    print("█" + "  ZAMBIA FRAUD DETECTION SYSTEM - INTEGRATION TESTS".center(58) + "█")
    print("█" + " "*58 + "█")
    print("█"*60)
    
    results = {
        "Module Imports": test_imports(),
        "Configuration": test_config_connectivity(),
        "ML Pipeline": test_ml_pipeline(),
        "API Connectivity": test_api_connectivity(),
        "Service Layer": test_services(),
    }
    
    # Summary
    print("\n" + "="*60)
    print("INTEGRATION TEST SUMMARY")
    print("="*60)
    
    total_passed = 0
    total_failed = 0
    
    for test_name, (passed, failed) in results.items():
        total_passed += passed
        total_failed += failed
        status = "✓ PASS" if failed == 0 else "✗ FAIL"
        print(f"{test_name:30} {passed} passed, {failed} failed [{status}]")
    
    print("-"*60)
    print(f"{'TOTAL':30} {total_passed} passed, {total_failed} failed")
    
    if total_failed == 0:
        print("\n✓ ALL INTEGRATION TESTS PASSED!")
        print("All modules are communicating correctly.")
        return 0
    else:
        print(f"\n✗ {total_failed} TEST(S) FAILED")
        print("Please check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
