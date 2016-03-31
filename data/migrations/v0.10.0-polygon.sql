UPDATE planet_osm_polygon
SET mz_poi_min_zoom = mz_calculate_min_zoom_pois(planet_osm_polygon.*)
WHERE
  amenity = 'boat_rental' OR
  shop = 'boat_rental' OR
  tags->'rental' = 'boat' OR
  (shop = 'boat' AND tags->'rental' = 'yes') OR
  man_made IN ('beacon', 'cross', 'mineshaft', 'adit', 'water_well') OR
  "natural" IN ('saddle', 'dune', 'geyser', 'sinkhole', 'hot_spring', 'rock', 'stone') OR
  highway = 'trailhead' OR
  whitewater IN ('put_in;egress', 'put_in', 'egress', 'hazard', 'rapid');

UPDATE planet_osm_polygon
SET mz_landuse_min_zoom = mz_calculate_min_zoom_landuse(planet_osm_polygon.*)
WHERE
  "natural" = 'scree';
