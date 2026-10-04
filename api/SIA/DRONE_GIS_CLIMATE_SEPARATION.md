# Drone, GIS, and Climate Module Separation

## Overview
The combined `drone_gis_climate.py` module has been separated into three independent modules for better organization and maintainability:

1. **`drone.py`** - Drone survey operations
2. **`gis.py`** - Geographic Information System layers and features
3. **`climate.py`** - Climate and environmental resource data

## Key Changes

### 1. Module Structure

#### **drone.py**
- **Collections:** 
  - `sia_drone_mission`
  - `sia_drone_operator`
  - `sia_drone_platform`
  - `sia_drone_capture_plan`
  - `sia_ground_control_point`
  - `sia_drone_field_condition`
  - `sia_drone_raw_data`
  - `sia_drone_quality_check`
  - `sia_drone_derived_product`

- **API Tag:** `SIA - Drone`
- **Main Endpoints:**
  - `POST /sia/drone-missions` - Create drone mission
  - `GET /sia/sites/{site_id}/drone-missions` - Get missions by site
  - `GET /sia/cases/{case_id}/drone-missions` - Get missions by case
  - All child resources linked to missions

#### **gis.py**
- **Collections:**
  - `sia_gis_layer`
  - `sia_gis_feature`
  - `sia_external_geo_source`

- **API Tag:** `SIA - GIS`
- **Main Endpoints:**
  - `POST /sia/gis-layers` - Create GIS layer
  - `GET /sia/sites/{site_id}/gis-layers` - Get layers by site
  - `GET /sia/cases/{case_id}/gis-layers` - Get layers by case
  - `POST /sia/gis-features` - Add features to layers
  - `POST /sia/external-geo-sources` - Register external data sources

#### **climate.py**
- **Collections:**
  - `sia_climate_resource`

- **API Tag:** `SIA - Climate`
- **Main Endpoints:**
  - `POST /sia/climate-resources` - Create climate resource
  - `GET /sia/sites/{site_id}/climate-resources` - Get resources by site
  - `GET /sia/cases/{case_id}/climate-resources` - Get resources by case
  - `POST /sia/climate-resources/bulk` - Bulk import climate data
  - `GET /sia/sites/{site_id}/climate-summary` - Get summary by type

## Scope Management

All three modules properly inherit from `SIAScope` and use the `apply_scope()` function to ensure:

### **Required from Frontend:**
- `sia_case_id` - MUST be provided when creating top-level records (missions, layers, climate resources)
- `site_id` - MUST be provided when creating top-level records

### **Inherited from Parent:**
- Child records (operators, platforms, features, etc.) inherit scope from their parent
- The `apply_scope()` function validates the entire parent chain
- Ensures data integrity across the hierarchy

### **Example Flow:**
```python
# Frontend provides case and site when creating a drone mission
POST /sia/drone-missions
{
  "sia_case_id": "case-123",
  "site_id": "site-456",
  "mission_code": "DM-001",
  ...
}

# Operator inherits scope from mission
POST /sia/drone-operators
{
  "drone_mission_id": "mission-789",  # Scope inherited from this
  "user_id": "user-001",
  ...
}
```

## API Endpoints Comparison

### Old Combined Module
```
Tag: SIA - Drone, GIS & Climate
- All endpoints mixed together
- Hard to navigate in API docs
```

### New Separated Modules

**Drone Module:**
```
Tag: SIA - Drone
POST   /sia/drone-missions
GET    /sia/drone-missions/{mission_id}
GET    /sia/sites/{site_id}/drone-missions
GET    /sia/cases/{case_id}/drone-missions
POST   /sia/drone-operators
GET    /sia/drone-missions/{mission_id}/operators
POST   /sia/drone-platforms
POST   /sia/drone-capture-plans
POST   /sia/ground-control-points
POST   /sia/drone-field-conditions
POST   /sia/drone-raw-data
POST   /sia/drone-quality-checks
POST   /sia/drone-derived-products
```

**GIS Module:**
```
Tag: SIA - GIS
POST   /sia/gis-layers
GET    /sia/gis-layers/{layer_id}
GET    /sia/sites/{site_id}/gis-layers
GET    /sia/cases/{case_id}/gis-layers
PATCH  /sia/gis-layers/{layer_id}
POST   /sia/gis-features
GET    /sia/gis-layers/{layer_id}/features
GET    /sia/gis-features/{feature_id}
PATCH  /sia/gis-features/{feature_id}
POST   /sia/external-geo-sources
GET    /sia/external-geo-sources/{source_id}
GET    /sia/sites/{site_id}/external-geo-sources
GET    /sia/cases/{case_id}/external-geo-sources
PATCH  /sia/external-geo-sources/{source_id}
```

**Climate Module:**
```
Tag: SIA - Climate
POST   /sia/climate-resources
GET    /sia/climate-resources/{resource_id}
GET    /sia/sites/{site_id}/climate-resources (with filters)
GET    /sia/cases/{case_id}/climate-resources
GET    /sia/sites/{site_id}/climate-summary
PATCH  /sia/climate-resources/{resource_id}
DELETE /sia/climate-resources/{resource_id}
POST   /sia/climate-resources/bulk
GET    /sia/climate-resource-types
GET    /sia/climate-reliability-levels
```

## Initialization

Each module has its own initialization function:

```python
from api.SIA.drone import init_drone_collections
from api.SIA.gis import init_gis_collections
from api.SIA.climate import init_climate_collections

# Call during app startup
await init_drone_collections()
await init_gis_collections()
await init_climate_collections()
```

## Frontend Integration Guidelines

### 1. **Always Provide Case and Site Context**
When creating top-level resources, the frontend MUST provide:
```javascript
// Drone Mission
const missionData = {
  sia_case_id: selectedCase.id,  // From case selector
  site_id: selectedSite.id,       // From site selector
  mission_code: "DM-001",
  // ... other fields
};

// GIS Layer
const layerData = {
  sia_case_id: selectedCase.id,
  site_id: selectedSite.id,
  layer_name: "Transmission Lines",
  // ... other fields
};

// Climate Resource
const climateData = {
  sia_case_id: selectedCase.id,
  site_id: selectedSite.id,
  resource_type: "SOLAR_RESOURCE",
  // ... other fields
};
```

### 2. **Child Resources Inherit Scope**
When creating child resources, only provide the parent ID:
```javascript
// Drone Operator (scope inherited from mission)
const operatorData = {
  drone_mission_id: mission.id,  // Scope comes from this
  user_id: currentUser.id,
  // ... other fields
};

// GIS Feature (scope inherited from layer)
const featureData = {
  gis_layer_id: layer.id,  // Scope comes from this
  feature_name: "Pole 001",
  // ... other fields
};
```

### 3. **Query Patterns**
```javascript
// Get all drone missions for a site
GET /api/sia/sites/${siteId}/drone-missions

// Get all GIS layers for a case
GET /api/sia/cases/${caseId}/gis-layers

// Get climate resources with filtering
GET /api/sia/sites/${siteId}/climate-resources?resource_type=SOLAR_RESOURCE&reliability_status=VERIFIED

// Get climate summary
GET /api/sia/sites/${siteId}/climate-summary
```

## Benefits of Separation

1. **Better Organization** - Clear separation of concerns
2. **Easier Navigation** - API docs are more organized with separate tags
3. **Improved Maintainability** - Each module can be updated independently
4. **Better Testing** - Can test each domain separately
5. **Clearer Documentation** - Each module has focused, domain-specific documentation
6. **Reduced Complexity** - Smaller, more focused files are easier to understand
7. **Scalability** - Each module can grow independently without affecting others

## Migration Notes

### For Backend Developers
1. Import the new separate modules in `main.py`
2. Each module has its own router and initialization function
3. All existing API endpoints remain the same (no breaking changes)
4. Only the internal organization has changed

### For Frontend Developers
1. **No breaking changes** - All API endpoints remain exactly the same
2. API documentation now shows three separate tags for better navigation
3. Continue providing `sia_case_id` and `site_id` as before
4. The scope validation is now more robust with better error messages

## Climate Module Enhancements

The climate module includes additional features:

### Resource Types
Comprehensive list including:
- Solar: GHI, DNI, DHI, irradiance
- Temperature: ambient, min, max
- Precipitation: rainfall, snow, ice
- Wind: speed, direction
- Environmental: humidity, corrosion, seismic, flood risk

### Reliability Levels
- MEASURED - Direct site measurement
- VERIFIED - Verified from reliable source
- PROVISIONAL - From reputable source, not verified
- INTERPOLATED - Interpolated from nearby stations
- MODELED - Climate model output
- ASSUMED - Engineering assumption
- UNVERIFIED - Uncertain origin

### Bulk Operations
Supports bulk import of climate datasets:
```javascript
POST /api/sia/climate-resources/bulk
{
  "sia_case_id": "case-123",
  "site_id": "site-456",
  "resources": [
    { "resource_type": "SOLAR_GHI", "parameter_value": 5.2, ... },
    { "resource_type": "TEMPERATURE", "parameter_value": 28.5, ... },
    // ... more resources
  ]
}
```

## Testing Checklist

- [ ] Verify drone mission creation with case/site
- [ ] Verify GIS layer creation with case/site
- [ ] Verify climate resource creation with case/site
- [ ] Verify child resources inherit scope correctly
- [ ] Verify query by site works for all modules
- [ ] Verify query by case works for all modules
- [ ] Test bulk climate import
- [ ] Test climate summary endpoint
- [ ] Verify API documentation shows three separate tags
- [ ] Verify error messages are clear when scope is missing

## File Changes

### New Files
- `backend/api/SIA/drone.py`
- `backend/api/SIA/gis.py`
- `backend/api/SIA/climate.py`
- `backend/api/SIA/DRONE_GIS_CLIMATE_SEPARATION.md` (this file)

### Modified Files
- `backend/main.py` - Updated imports and router registration

### Deprecated Files
- `backend/api/SIA/drone_gis_climate.py` - Keep for reference, but no longer imported
