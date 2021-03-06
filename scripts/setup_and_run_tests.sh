#!/bin/bash

set -e

dbname="vector_datasource_$$"
basedir="$(dirname ${BASH_SOURCE[0]})/.."
server_pid=0

function die {
   echo "$@" 1>&2;
   exit 1
}

for prog in createdb cat dropdb python osm2pgsql shp2pgsql xargs zip; do
   which "${prog}" >/dev/null || die "Unable to find '${prog}' program in PATH."
done

echo "=== Creating database \"${dbname}\"..."
createdb -E UTF-8 -T template0 "${dbname}"
cat >empty.osm <<EOF
<?xml version='1.0' encoding='utf-8'?>
<osm version="0.6">
</osm>
EOF

function cleanup {
   if [[ $server_pid -ne 0 ]]; then
      echo "=== Killing test server ==="
      kill -HUP "${server_pid}"
   fi
   echo "=== Dropping database \"${dbname}\" and cleaning up..."
   dropdb --if-exists "${dbname}"
   rm -f empty.osm data.osc
}

# set the env var $NOCLEANUP to anything and the code won't clean up. this is
# useful when developing to see what the intermediate state is.
if [[ -z $NOCLEANUP ]]; then
    trap cleanup EXIT
fi

echo "=== Enabling database extensions..."
for ext in postgis hstore; do
   psql -d "${dbname}" -c "CREATE EXTENSION ${ext}"
done

echo "=== Dumping test data..."
if [[ -f data.osc ]]; then
    rm -f data.osc
fi
python "${basedir}/test.py" -dumpdata

echo "=== Loading test data..."
osm2pgsql -E 900913 -s -C 1024 -S "${basedir}/osm2pgsql.style" \
  -d "${dbname}" -k --create empty.osm
osm2pgsql -E 900913 -s -C 1024 -S "${basedir}/osm2pgsql.style" \
  -d "${dbname}" -k --append data.osc

echo "=== Loading external data..."
# mock these tables - the shapefiles are _huge_ and we don't want to
# spend time downloading and importing them - we use smaller extracts
# in test/fixtures/ to handle specific test cases.
psql "${dbname}" <<EOF
CREATE TABLE water_polygons (
    gid SERIAL,
    fid double precision,
    the_geom geometry(MultiPolygon,900913)
);
CREATE TABLE land_polygons (
    gid SERIAL,
    fid double precision,
    the_geom geometry(MultiPolygon,900913)
);
CREATE TABLE simplified_land_polygons (
    gid SERIAL,
    fid double precision,
    the_geom geometry(MultiPolygon,900913)
);
EOF
# load up shapefile fixtures into the appropriate tables
for tbl in `ls ${basedir}/test/fixtures/`; do
    if [[ -d "${basedir}/test/fixtures/${tbl}" ]]; then
        for shp in "${basedir}/test/fixtures/${tbl}"/*.shp; do
            shp2pgsql -a -s 900913 -W Windows-1252 -g the_geom \
                      "${shp}" "${tbl}" \
                | psql -d "${dbname}"
        done
    fi
done

pushd "${basedir}/data"
# Unzip all zip
ls *.zip | xargs -n1 unzip -o
# Load data from zips
./shp2pgsql.sh | psql -d "${dbname}"
# Add indexes and any required database updates
./perform-sql-updates.sh -d "${dbname}"
popd

#echo "=== Loading Who's on First data..."
# Finally, neighbourhood data is required to be loaded from Who's on First.
#wget https://s3.amazonaws.com/mapzen-tiles-prod-us-east/data/wof/wof_neighbourhoods.pgdump
#pg_restore --clean --if-exists -d "${dbname}" -O wof_neighbourhoods.pgdump

# make config for tileserver and serve
test_server_port="${basedir}/test_server.port"
rm -f "${test_server_port}"
python scripts/test_server.py "${dbname}" "${USER}" "${test_server_port}" &
server_pid=$!

# wait for file to exist
if [[ ! -f "${test_server_port}" ]]; then
    sleep 1
fi

if [[ ! -f "${test_server_port}" ]]; then
    echo "Test server didn't start up within 1s."
    exit 1
fi

# run tests
port=`cat "${test_server_port}"`
export VECTOR_DATASOURCE_CONFIG_URL="http://localhost:${port}/%(layer)s/%(z)d/%(x)d/%(y)d.json"
python "${basedir}/test.py" || (cat test.log; exit 1)

echo "SUCCESS"

# no longer an error to fail - all tests are done.
set +e
kill -HUP "${server_pid}"
wait
