UPDATE planet_osm_line
  SET mz_road_level = mz_calculate_min_zoom_roads(planet_osm_line.*)
  WHERE
    highway = 'raceway' AND
    COALESCE(mz_road_level, 999) <> COALESCE(mz_calculate_min_zoom_roads(planet_osm_line.*), 999);
