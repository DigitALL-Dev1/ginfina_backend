"""Quick test script to verify the separated Drone, GIS, and Climate modules.

Run from backend directory:
    python -B test_separated_modules.py

This script verifies:
1. All three modules can be imported successfully
2. Routers are properly configured
3. Collections are accessible
4. Initialization functions work
"""
import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(override=True)


async def test_imports():
    """Test that all modules can be imported."""
    print("\n" + "="*60)
    print("Testing Module Imports")
    print("="*60)
    
    try:
        from api.SIA import drone, gis, climate
        print("✓ All modules imported successfully")
        
        # Check routers
        assert hasattr(drone, 'router'), "drone module missing router"
        assert hasattr(gis, 'router'), "gis module missing router"
        assert hasattr(climate, 'router'), "climate module missing router"
        print("✓ All routers found")
        
        # Check initialization functions
        assert hasattr(drone, 'init_drone_collections'), "drone module missing init function"
        assert hasattr(gis, 'init_gis_collections'), "gis module missing init function"
        assert hasattr(climate, 'init_climate_collections'), "climate module missing init function"
        print("✓ All initialization functions found")
        
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False


async def test_database_connection():
    """Test database connectivity."""
    print("\n" + "="*60)
    print("Testing Database Connection")
    print("="*60)
    
    try:
        from api.SIA.drone import client as drone_client
        await asyncio.wait_for(drone_client.admin.command("ping"), timeout=5)
        print("✓ Database connection successful")
        return True
    except asyncio.TimeoutError:
        print("✗ Database connection timeout")
        return False
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        return False


async def test_initialization():
    """Test collection initialization."""
    print("\n" + "="*60)
    print("Testing Collection Initialization")
    print("="*60)
    
    try:
        from api.SIA.drone import init_drone_collections
        from api.SIA.gis import init_gis_collections
        from api.SIA.climate import init_climate_collections
        
        await init_drone_collections()
        print("✓ Drone collections initialized")
        
        await init_gis_collections()
        print("✓ GIS collections initialized")
        
        await init_climate_collections()
        print("✓ Climate collections initialized")
        
        return True
    except Exception as e:
        print(f"✗ Initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_routes():
    """Test that routes are properly configured."""
    print("\n" + "="*60)
    print("Testing Route Configuration")
    print("="*60)
    
    try:
        from api.SIA.drone import router as drone_router
        from api.SIA.gis import router as gis_router
        from api.SIA.climate import router as climate_router
        
        # Count routes
        drone_routes = len(drone_router.routes)
        gis_routes = len(gis_router.routes)
        climate_routes = len(climate_router.routes)
        
        print(f"✓ Drone module: {drone_routes} routes")
        print(f"✓ GIS module: {gis_routes} routes")
        print(f"✓ Climate module: {climate_routes} routes")
        print(f"✓ Total: {drone_routes + gis_routes + climate_routes} routes")
        
        return True
    except Exception as e:
        print(f"✗ Route configuration failed: {e}")
        return False


async def test_scope_inheritance():
    """Test that SIAScope is properly inherited."""
    print("\n" + "="*60)
    print("Testing Scope Inheritance")
    print("="*60)
    
    try:
        from api.SIA.drone import DroneMissionCreate
        from api.SIA.gis import GISLayerCreate
        from api.SIA.climate import ClimateResourceCreate
        from api.SIA.scope import SIAScope
        
        # Check inheritance
        assert issubclass(DroneMissionCreate, SIAScope), "DroneMissionCreate must inherit from SIAScope"
        assert issubclass(GISLayerCreate, SIAScope), "GISLayerCreate must inherit from SIAScope"
        assert issubclass(ClimateResourceCreate, SIAScope), "ClimateResourceCreate must inherit from SIAScope"
        
        print("✓ DroneMissionCreate inherits from SIAScope")
        print("✓ GISLayerCreate inherits from SIAScope")
        print("✓ ClimateResourceCreate inherits from SIAScope")
        
        # Check that scope fields exist
        drone_fields = DroneMissionCreate.model_fields
        gis_fields = GISLayerCreate.model_fields
        climate_fields = ClimateResourceCreate.model_fields
        
        assert 'sia_case_id' in drone_fields, "DroneMissionCreate missing sia_case_id"
        assert 'site_id' in drone_fields, "DroneMissionCreate missing site_id"
        assert 'sia_case_id' in gis_fields, "GISLayerCreate missing sia_case_id"
        assert 'site_id' in gis_fields, "GISLayerCreate missing site_id"
        assert 'sia_case_id' in climate_fields, "ClimateResourceCreate missing sia_case_id"
        assert 'site_id' in climate_fields, "ClimateResourceCreate missing site_id"
        
        print("✓ All models have required scope fields (sia_case_id, site_id)")
        
        return True
    except Exception as e:
        print(f"✗ Scope inheritance test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("GINFINIA - Separated Modules Test Suite")
    print("="*60)
    
    results = []
    
    # Run tests
    results.append(("Import Test", await test_imports()))
    results.append(("Database Connection", await test_database_connection()))
    results.append(("Collection Initialization", await test_initialization()))
    results.append(("Route Configuration", await test_routes()))
    results.append(("Scope Inheritance", await test_scope_inheritance()))
    
    # Summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status} - {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓ All tests passed! The modules are ready to use.")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed. Please review the errors above.")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nTest suite crashed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
