# Frontend Integration Guide - Drone, GIS, and Climate Modules

## Quick Reference

### 🚨 Critical Requirements
1. **ALWAYS** provide `sia_case_id` and `site_id` when creating top-level resources
2. **NEVER** hardcode these values - always get them from user selection
3. Child resources automatically inherit scope from their parent

---

## Module Overview

| Module | Purpose | Top-Level Resource | Scope Required |
|--------|---------|-------------------|----------------|
| **Drone** | Drone surveys & photogrammetry | Drone Mission | ✅ Yes |
| **GIS** | Geographic layers & features | GIS Layer | ✅ Yes |
| **Climate** | Climate & environmental data | Climate Resource | ✅ Yes |

---

## 1. Drone Module

### Create Drone Mission (Top-Level)
```javascript
// REQUIRED: Get case and site from user selection
const selectedCase = getCurrentCase(); // Your case selector
const selectedSite = getCurrentSite(); // Your site selector

const response = await fetch('/api/sia/drone-missions', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    sia_case_id: selectedCase.id,      // ✅ REQUIRED
    site_id: selectedSite.id,           // ✅ REQUIRED
    mission_code: "DM-001",
    mission_purpose: "Site Survey - Phase 1",
    target_discipline: "ELECTRICAL",
    planned_date: "2024-03-15",
    mission_status: "PLANNED"
  })
});
```

### Add Operator (Child - Scope Inherited)
```javascript
// Scope automatically inherited from mission
const response = await fetch('/api/sia/drone-operators', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    drone_mission_id: mission.id,  // Parent reference
    user_id: operator.id,
    competency_ref: "UAV-CERT-2024",
    permission_ref: "FLIGHT-PERMIT-001"
  })
});
```

### Query Patterns
```javascript
// Get all missions for a site
const missions = await fetch(`/api/sia/sites/${siteId}/drone-missions`);

// Get all missions for a case
const missions = await fetch(`/api/sia/cases/${caseId}/drone-missions`);

// Get mission details
const mission = await fetch(`/api/sia/drone-missions/${missionId}`);

// Get operators for a mission
const operators = await fetch(`/api/sia/drone-missions/${missionId}/operators`);
```

---

## 2. GIS Module

### Create GIS Layer (Top-Level)
```javascript
// REQUIRED: Get case and site from user selection
const response = await fetch('/api/sia/gis-layers', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    sia_case_id: selectedCase.id,      // ✅ REQUIRED
    site_id: selectedSite.id,           // ✅ REQUIRED
    layer_name: "Transmission Lines",
    layer_type: "INFRASTRUCTURE",
    geometry_type: "LINE",
    source_name: "Site Survey 2024",
    crs: "EPSG:32637",
    reliability_status: "VERIFIED",
    is_active: true
  })
});
```

### Add GIS Feature (Child - Scope Inherited)
```javascript
// Scope automatically inherited from layer
const response = await fetch('/api/sia/gis-features', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    gis_layer_id: layer.id,  // Parent reference
    feature_code: "TL-001",
    feature_name: "11kV Transmission Line",
    feature_type: "CABLE",
    geometry_data: "LINESTRING(36.8 -1.3, 36.9 -1.2)",
    attributes: {
      voltage: "11kV",
      length: 1500,
      material: "ACSR"
    },
    reliability_status: "VERIFIED"
  })
});
```

### Update GIS Layer
```javascript
const response = await fetch(`/api/sia/gis-layers/${layerId}`, {
  method: 'PATCH',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    reliability_status: "VERIFIED",
    remarks: "Updated after field verification"
  })
});
```

### Query Patterns
```javascript
// Get all layers for a site
const layers = await fetch(`/api/sia/sites/${siteId}/gis-layers`);

// Get all layers for a case
const layers = await fetch(`/api/sia/cases/${caseId}/gis-layers`);

// Get features in a layer
const features = await fetch(`/api/sia/gis-layers/${layerId}/features`);

// Register external geo source
const source = await fetch('/api/sia/external-geo-sources', {
  method: 'POST',
  body: JSON.stringify({
    sia_case_id: selectedCase.id,
    site_id: selectedSite.id,
    provider_name: "NASA SRTM",
    dataset_name: "SRTM 30m DEM",
    source_type: "SATELLITE_IMAGERY",
    source_reference: "https://earthdata.nasa.gov/...",
    reliability_status: "VERIFIED"
  })
});
```

---

## 3. Climate Module

### Create Climate Resource (Top-Level)
```javascript
// REQUIRED: Get case and site from user selection
const response = await fetch('/api/sia/climate-resources', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    sia_case_id: selectedCase.id,      // ✅ REQUIRED
    site_id: selectedSite.id,           // ✅ REQUIRED
    resource_type: "SOLAR_GHI",
    parameter_name: "Annual Global Horizontal Irradiance",
    parameter_value: 5.8,
    unit: "kWh/m²/day",
    period_from: "2020-01-01",
    period_to: "2023-12-31",
    temporal_granularity: "ANNUAL",
    source_name: "NASA POWER",
    reliability_status: "VERIFIED",
    confidence_level: "HIGH"
  })
});
```

### Bulk Import Climate Data
```javascript
const response = await fetch('/api/sia/climate-resources/bulk', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    sia_case_id: selectedCase.id,
    site_id: selectedSite.id,
    resources: [
      {
        resource_type: "SOLAR_GHI",
        parameter_name: "Annual GHI",
        parameter_value: 5.8,
        unit: "kWh/m²/day",
        reliability_status: "VERIFIED"
      },
      {
        resource_type: "TEMPERATURE",
        parameter_name: "Mean Annual Temperature",
        parameter_value: 28.5,
        unit: "°C",
        reliability_status: "VERIFIED"
      },
      {
        resource_type: "WIND_SPEED",
        parameter_name: "Annual Average Wind Speed",
        parameter_value: 3.2,
        unit: "m/s",
        measurement_height: 10,
        reliability_status: "VERIFIED"
      }
    ]
  })
});
```

### Query Patterns
```javascript
// Get all climate resources for a site
const resources = await fetch(`/api/sia/sites/${siteId}/climate-resources`);

// Get filtered climate resources
const solar = await fetch(
  `/api/sia/sites/${siteId}/climate-resources?resource_type=SOLAR_GHI&reliability_status=VERIFIED`
);

// Get climate summary by type
const summary = await fetch(`/api/sia/sites/${siteId}/climate-summary`);
// Returns: [
//   { resource_type: "SOLAR_GHI", parameter_count: 5, latest_updated: "..." },
//   { resource_type: "TEMPERATURE", parameter_count: 12, latest_updated: "..." }
// ]

// Update climate resource
await fetch(`/api/sia/climate-resources/${resourceId}`, {
  method: 'PATCH',
  body: JSON.stringify({
    reliability_status: "VERIFIED",
    confidence_level: "HIGH"
  })
});

// Delete climate resource
await fetch(`/api/sia/climate-resources/${resourceId}`, {
  method: 'DELETE'
});

// Get available resource types
const types = await fetch('/api/sia/climate-resource-types');

// Get reliability levels
const levels = await fetch('/api/sia/climate-reliability-levels');
```

---

## Error Handling

### Missing Scope Fields
```javascript
// ❌ BAD - Will fail with 422 error
const response = await fetch('/api/sia/drone-missions', {
  method: 'POST',
  body: JSON.stringify({
    mission_code: "DM-001"
    // Missing sia_case_id and site_id!
  })
});
// Error: "Select an SIA case and site before saving this record"
```

```javascript
// ✅ GOOD - Includes required scope
const response = await fetch('/api/sia/drone-missions', {
  method: 'POST',
  body: JSON.stringify({
    sia_case_id: selectedCase.id,
    site_id: selectedSite.id,
    mission_code: "DM-001"
  })
});
```

### Invalid Parent Reference
```javascript
// ❌ BAD - Invalid mission ID
const response = await fetch('/api/sia/drone-operators', {
  method: 'POST',
  body: JSON.stringify({
    drone_mission_id: "invalid-id",
    user_id: "user-001"
  })
});
// Error: "drone_mission_id 'invalid-id' not found"
```

---

## Component Examples

### React Component - Drone Mission Form
```jsx
import { useState } from 'react';

function DroneMissionForm({ selectedCase, selectedSite }) {
  const [formData, setFormData] = useState({
    mission_code: '',
    mission_purpose: '',
    target_discipline: 'ELECTRICAL',
    planned_date: '',
    mission_status: 'PLANNED'
  });

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Validate scope
    if (!selectedCase?.id || !selectedSite?.id) {
      alert('Please select a case and site first');
      return;
    }

    try {
      const response = await fetch('/api/sia/drone-missions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sia_case_id: selectedCase.id,  // From props/context
          site_id: selectedSite.id,      // From props/context
          ...formData
        })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail);
      }

      const mission = await response.json();
      console.log('Mission created:', mission);
      // Navigate to mission details or refresh list
    } catch (error) {
      console.error('Failed to create mission:', error);
      alert(error.message);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      {/* Form fields */}
      <button type="submit">Create Mission</button>
    </form>
  );
}
```

### Vue Component - Climate Resource List
```vue
<template>
  <div>
    <div class="filters">
      <select v-model="resourceTypeFilter">
        <option value="">All Types</option>
        <option v-for="type in resourceTypes" :key="type">{{ type }}</option>
      </select>
      <select v-model="reliabilityFilter">
        <option value="">All Reliability</option>
        <option value="VERIFIED">Verified</option>
        <option value="PROVISIONAL">Provisional</option>
      </select>
    </div>

    <table>
      <tr v-for="resource in filteredResources" :key="resource.id">
        <td>{{ resource.resource_type }}</td>
        <td>{{ resource.parameter_name }}</td>
        <td>{{ resource.parameter_value }} {{ resource.unit }}</td>
        <td>{{ resource.reliability_status }}</td>
      </tr>
    </table>
  </div>
</template>

<script>
export default {
  props: ['siteId'],
  data() {
    return {
      resources: [],
      resourceTypes: [],
      resourceTypeFilter: '',
      reliabilityFilter: ''
    };
  },
  computed: {
    filteredResources() {
      return this.resources.filter(r => 
        (!this.resourceTypeFilter || r.resource_type === this.resourceTypeFilter) &&
        (!this.reliabilityFilter || r.reliability_status === this.reliabilityFilter)
      );
    }
  },
  async mounted() {
    await this.loadResourceTypes();
    await this.loadResources();
  },
  methods: {
    async loadResourceTypes() {
      const response = await fetch('/api/sia/climate-resource-types');
      this.resourceTypes = await response.json();
    },
    async loadResources() {
      let url = `/api/sia/sites/${this.siteId}/climate-resources`;
      const params = new URLSearchParams();
      if (this.resourceTypeFilter) params.append('resource_type', this.resourceTypeFilter);
      if (this.reliabilityFilter) params.append('reliability_status', this.reliabilityFilter);
      if (params.toString()) url += `?${params}`;

      const response = await fetch(url);
      this.resources = await response.json();
    }
  },
  watch: {
    resourceTypeFilter: 'loadResources',
    reliabilityFilter: 'loadResources'
  }
};
</script>
```

---

## Testing Checklist

### Before Release
- [ ] Case and site selectors are properly implemented
- [ ] All create forms include sia_case_id and site_id
- [ ] Error messages are displayed to users
- [ ] Loading states are shown during API calls
- [ ] Success/failure feedback is provided
- [ ] Lists refresh after create/update/delete operations
- [ ] Child resources don't ask for scope fields
- [ ] Update operations don't try to modify scope fields

### API Testing
```bash
# Test with cURL

# 1. Create drone mission (replace IDs with real values)
curl -X POST http://localhost:8001/api/sia/drone-missions \
  -H "Content-Type: application/json" \
  -d '{
    "sia_case_id": "case-123",
    "site_id": "site-456",
    "mission_code": "TEST-DM-001",
    "mission_purpose": "API Test"
  }'

# 2. Get missions for site
curl http://localhost:8001/api/sia/sites/site-456/drone-missions

# 3. Create GIS layer
curl -X POST http://localhost:8001/api/sia/gis-layers \
  -H "Content-Type: application/json" \
  -d '{
    "sia_case_id": "case-123",
    "site_id": "site-456",
    "layer_name": "Test Layer"
  }'

# 4. Create climate resource
curl -X POST http://localhost:8001/api/sia/climate-resources \
  -H "Content-Type: application/json" \
  -d '{
    "sia_case_id": "case-123",
    "site_id": "site-456",
    "resource_type": "SOLAR_GHI",
    "parameter_name": "Test Solar",
    "parameter_value": 5.5,
    "unit": "kWh/m²/day",
    "reliability_status": "PROVISIONAL"
  }'
```

---

## Support

### Common Issues

**Issue:** "Select an SIA case and site before saving this record"
- **Cause:** Missing sia_case_id or site_id
- **Fix:** Ensure your form includes these fields from user selection

**Issue:** "X not found"
- **Cause:** Invalid parent ID reference
- **Fix:** Verify the parent record exists before creating child

**Issue:** Scope mismatch
- **Cause:** Child's scope doesn't match parent
- **Fix:** Don't manually set scope on child records - let it inherit

### Need Help?
- Check API docs at `/docs` endpoint
- Review the module separation guide: `DRONE_GIS_CLIMATE_SEPARATION.md`
- Test using the provided test script: `python -B test_separated_modules.py`
