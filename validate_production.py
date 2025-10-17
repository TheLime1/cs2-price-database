"""
Production Readiness Validator
Checks that the codebase is ready for production deployment
"""
import os
import sys
import json
from pathlib import Path


def print_status(check_name: str, passed: bool, details: str = ""):
    """Print check status with color"""
    status = "[PASS]" if passed else "[FAIL]"
    print(f"{status} {check_name}")
    if details:
        print(f"       {details}")


def check_required_files():
    """Check that all required files exist"""
    print("\n=== Checking Required Files ===")

    required_files = [
        ("README.md", "Main documentation"),
        ("requirements.txt", "Python dependencies"),
        ("collect_prices.py", "Main collection script"),
        ("high_speed_scraper.py", "Worker stealing scraper"),
        ("csgoskins_scraper.py", "Wear range scraper"),
        ("migrate_database_v3.py", "Migration script"),
        (".env.example", "Environment template"),
        ("PRODUCTION_CHECKLIST.md", "Deployment guide"),
    ]

    all_exist = True
    for filename, description in required_files:
        exists = os.path.exists(filename)
        print_status(f"{description} ({filename})", exists)
        all_exist = all_exist and exists

    return all_exist


def check_test_files_removed():
    """Check that test/debug files are removed"""
    print("\n=== Checking Test Files Removed ===")

    test_patterns = [
        "test_*.py",
        "debug_*.py",
        "*_test.py",
        "page_source_debug.html",
    ]

    all_clean = True
    for pattern in test_patterns:
        files = list(Path(".").glob(pattern))
        if files:
            print_status(f"No {pattern} files", False,
                         f"Found: {', '.join(str(f) for f in files)}")
            all_clean = False
        else:
            print_status(f"No {pattern} files", True)

    return all_clean


def check_database_structure():
    """Check database exists and has correct structure"""
    print("\n=== Checking Database Structure ===")

    db_path = "data/skins_database.json"

    if not os.path.exists(db_path):
        print_status("Database exists", False, f"{db_path} not found")
        return False

    print_status("Database exists", True, db_path)

    try:
        with open(db_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # V3.0 format has metadata wrapper
        if isinstance(data, dict):
            if 'skins' in data:
                # V3.0 format with metadata
                print_status("Database has V3.0 format",
                             True, "With metadata wrapper")
                skins_list = data['skins']
            else:
                print_status("Database format", False,
                             "Unknown dict structure")
                return False
        elif isinstance(data, list):
            # Legacy format
            print_status("Database is a list", True, "Legacy format")
            skins_list = data
        else:
            print_status("Database format", False, f"Type: {type(data)}")
            return False

        if len(skins_list) == 0:
            print_status("Database has skins", False, "Database is empty")
            return False

        print_status("Database has skins", True, f"{len(skins_list)} total")

        # Check first skin structure
        sample = skins_list[0]
        required_fields = ["weapon", "skin_name", "variants"]
        v3_fields = ["wear_ranges", "has_stattrak"]

        for field in required_fields:
            has_field = field in sample
            print_status(f"Has '{field}' field", has_field)

        has_v3 = all(field in sample for field in v3_fields)
        print_status("Has V3.0 schema", has_v3,
                     "wear_ranges and has_stattrak fields")

        return True

    except json.JSONDecodeError as e:
        print_status("Database is valid JSON", False, str(e))
        return False
    except Exception as e:
        print_status("Database check", False, str(e))
        return False


def check_dependencies():
    """Check that all dependencies are listed"""
    print("\n=== Checking Dependencies ===")

    if not os.path.exists("requirements.txt"):
        print_status("requirements.txt exists", False)
        return False

    with open("requirements.txt", 'r') as f:
        deps = f.read()

    required_deps = [
        ("selenium", "WebDriver automation"),
        ("beautifulsoup4", "HTML parsing"),
        ("python-dotenv", "Environment variables"),
        ("requests", "HTTP requests"),
    ]

    all_present = True
    for dep, description in required_deps:
        present = dep in deps.lower()
        print_status(f"{description} ({dep})", present)
        all_present = all_present and present

    return all_present


def check_documentation():
    """Check that documentation is complete"""
    print("\n=== Checking Documentation ===")

    docs = [
        ("README.md", 5000, "Main README"),
        ("ALGORITHM_DETAILED.md", 10000, "Algorithm docs"),
        ("HIGH_SPEED_ARCHITECTURE.md", 2000, "Architecture docs"),
        ("V3_MIGRATION_COMPLETE.md", 5000, "Migration guide"),
        ("PRODUCTION_CHECKLIST.md", 3000, "Deployment guide"),
    ]

    all_good = True
    for filename, min_size, description in docs:
        if not os.path.exists(filename):
            print_status(f"{description} exists", False, filename)
            all_good = False
            continue

        size = os.path.getsize(filename)
        sufficient = size >= min_size
        print_status(
            f"{description} complete",
            sufficient,
            f"{filename} ({size:,} bytes, min: {min_size:,})"
        )
        all_good = all_good and sufficient

    return all_good


def check_cache_cleaned():
    """Check that cache directories are cleaned"""
    print("\n=== Checking Cache Cleaned ===")

    cache_dirs = [
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
    ]

    all_clean = True
    for dirname in cache_dirs:
        exists = os.path.exists(dirname)
        print_status(f"No {dirname}", not exists)
        all_clean = all_clean and not exists

    return all_clean


def check_env_template():
    """Check that .env.example is properly configured"""
    print("\n=== Checking Environment Template ===")

    if not os.path.exists(".env.example"):
        print_status(".env.example exists", False)
        return False

    with open(".env.example", 'r') as f:
        env_content = f.read()

    required_vars = [
        "WORKER_COUNT",
        "MAX_RETRIES",
        "HEADLESS_MODE",
        "LOG_LEVEL",
    ]

    all_present = True
    for var in required_vars:
        present = var in env_content
        print_status(f"Has {var}", present)
        all_present = all_present and present

    # Check no sensitive data
    sensitive_patterns = ["password", "secret", "key", "token"]
    has_sensitive = any(pattern in env_content.lower()
                        for pattern in sensitive_patterns)
    print_status("No sensitive data in template", not has_sensitive)

    return all_present and not has_sensitive


def main():
    """Run all production readiness checks"""
    print("=" * 60)
    print("CS2 Price Database - Production Readiness Check")
    print("=" * 60)

    checks = [
        ("Required Files", check_required_files),
        ("Test Files Removed", check_test_files_removed),
        ("Database Structure", check_database_structure),
        ("Dependencies", check_dependencies),
        ("Documentation", check_documentation),
        ("Cache Cleaned", check_cache_cleaned),
        ("Environment Template", check_env_template),
    ]

    results = {}
    for name, check_func in checks:
        try:
            results[name] = check_func()
        except Exception as e:
            print(f"\n[ERROR] {name} check failed: {e}")
            results[name] = False

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, passed_check in results.items():
        status = "[PASS]" if passed_check else "[FAIL]"
        print(f"{status} {name}")

    print(f"\nResult: {passed}/{total} checks passed")

    if passed == total:
        print("\n✅ PRODUCTION READY!")
        print("All checks passed. Ready for deployment.")
        return 0
    else:
        print(f"\n❌ NOT READY")
        print(f"{total - passed} check(s) failed. Review issues above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
