import json
import pyrosm
import pandas as pd
import geopandas as gpd
from tqdm import tqdm

OSM_KEYS = [
  "name",
  "highway",
  "access",
  "oneway",
  "bridge",
  "tunnel",
  "junction",
  "service",
  "maxspeed",
  "lanes",
  "lanes:forward",
  "lanes:backward",
  "width",
  "surface",
  "tracktype",
  "smoothness",
  "bicycle",
  "cycle_highway",
  "motor_vehicle",
  "cyclestreet",
  "bicycle_road",
  "cycleway",
  "cycleway:both",
  "cycleway:left",
  "cycleway:right",
  "foot",
  "footway",
  "sidewalk",
  "sidewalk:both",
  "sidewalk:left",
  "sidewalk:right",
  "sidewalk:foot",
  "segregated",
  "indoor",
  "tram",
  "traffic_sign",
  "traffic_sign:forward",
  "cycleway:bicycle",
  'cycleway:left:bicycle',
  'cycleway:left:lane',
  'cycleway:left:segregated',
  'cycleway:left:oneway',
  'cycleway:left:foot',
  'cycleway:left:traffic_sign',
  'cycleway:right:bicycle',
  'cycleway:right:lane',
  'cycleway:right:segregated',
  'cycleway:right:oneway',
  'cycleway:right:foot',
  'cycleway:right:traffic_sign',
  'cycleway:both:bicycle',
  'cycleway:both:lane',
  'cycleway:both:segregated',
  'cycleway:both:oneway',
  'cycleway:both:foot',
  'cycleway:both:traffic_sign',
  'sidewalk:left:bicycle',
  'sidewalk:left:segregated',
  'sidewalk:left:oneway',
  'sidewalk:left:foot',
  'sidewalk:left:traffic_sign',
  'sidewalk:right:bicycle',
  'sidewalk:right:segregated',
  'sidewalk:right:oneway',
  'sidewalk:right:foot',
  'sidewalk:right:traffic_sign',
  'sidewalk:both:bicycle',
  'sidewalk:both:segregated',
  'sidewalk:both:oneway',
  'sidewalk:both:foot',
  'sidewalk:both:traffic_sign'
]

OSM_KEYS = OSM_KEYS.copy()

is_segregated = lambda x: any((key for key, value in x.items() if 'segregated' in key and value == 'yes'))
is_not_accessible = lambda x: x.get('access') == 'no'
use_sidepath = lambda x: any((key for key, value in x.items() if 'bicycle' in key and value == 'use_sidepath'))

is_indoor = lambda x: x.get('indoor') == 'yes'

is_path = lambda x: x['highway'] in ['path']
is_track = lambda x: x['highway'] in ['track']
is_footway = lambda x: x['highway'] in ['footway', 'pedestrian']

can_walk_right = lambda x: x.get('foot') in ['yes', 'designated'] or any((key for key, value in x.items() if 'right:foot' in key and value in ['yes', 'designated'])) or x.get('sidewalk') in ['yes', 'separated', 'both', 'right', 'left'] or (x.get('sidewalk:right') in ['yes', 'separated', 'both', 'right']) or (x.get('sidewalk:both') in ['yes', 'separated', 'both'])
can_walk_left = lambda x: x.get('foot') in ['yes', 'designated'] or any((key for key, value in x.items() if 'left:foot' in key and value in ['yes', 'designated'])) or x.get('sidewalk') in ['yes', 'separated', 'both', 'right', 'left'] or (x.get('sidewalk:left') in ['yes', 'separated', 'both', 'left']) or (x.get('sidewalk:both') in ['yes', 'separated', 'both'])

can_bike = lambda x: x.get('bicycle') in ['yes', 'designated'] and x.get('highway') not in ['motorway', 'motorway_link']
cannot_bike = lambda x: x.get('bicycle') in ['no', 'dismount', 'use_sidepath'] or x.get('highway') in ['corridor', 'motorway', 'motorway_link', 'trunk', 'trunk_link'] or x.get('access') in ['customers']

is_obligated_segregated = lambda x: 'traffic_sign' in x.keys() and isinstance(x['traffic_sign'], str) and ('241' in x['traffic_sign']) or ('traffic_sign:forward' in x.keys() and isinstance(x['traffic_sign:forward'], str) and ('241' in x['traffic_sign:forward']))
is_obligated_shared = lambda x: 'traffic_sign' in x.keys() and isinstance(x['traffic_sign'], str) and ('240' in x['traffic_sign']) or ('traffic_sign:forward' in x.keys() and isinstance(x['traffic_sign:forward'], str) and ('240' in x['traffic_sign:forward']))

_is_sign_free_for_bicycle_use = lambda x: 'traffic_sign' in x.keys() and isinstance(x['traffic_sign'], str) and ('1022-10' in x['traffic_sign']) or ('traffic_sign:forward' in x.keys() and isinstance(x['traffic_sign:forward'], str) and ('1022-10' in x['traffic_sign:forward']))
_is_sign_buslane = lambda x: 'traffic_sign' in x.keys() and isinstance(x['traffic_sign'], str) and ('245' in x['traffic_sign']) or ('traffic_sign:forward' in x.keys() and isinstance(x['traffic_sign:forward'], str) and ('245' in x['traffic_sign:forward']))
_is_sign_footway = lambda x: 'traffic_sign' in x.keys() and isinstance(x['traffic_sign'], str) and ('239' in x['traffic_sign'] or '242.1' in x['traffic_sign']) or ('traffic_sign:forward' in x.keys() and isinstance(x['traffic_sign:forward'], str) and ('239' in x['traffic_sign:forward'] or '242.1' in x['traffic_sign:forward']))
is_sign_shared_way = lambda x: _is_sign_footway(x) and _is_sign_free_for_bicycle_use(x)
is_sign_shared_buslane = lambda x: _is_sign_buslane(x) and _is_sign_free_for_bicycle_use(x)

is_designated = lambda x: x.get('bicycle') == 'designated'

is_bicycle_designated_left = lambda x: (is_designated(x) or x.get('cycleway:left:bicycle') == 'designated') or x.get('cycleway:bicycle') == 'designated'
is_bicycle_designated_right = lambda x: is_designated(x) or x.get('cycleway:right:bicycle') == 'designated' or x.get('cycleway:bicycle') == 'designated'

is_pedestrian_designated_left = lambda x: x.get('foot') == 'designated' or x.get('sidewalk:left:foot') == 'designated' or x.get('sidewalk:foot') == 'designated'
is_pedestrian_designated_right = lambda x: x.get('foot') == 'designated' or x.get('sidewalk:right:foot') == 'designated' or x.get('sidewalk:foot') == 'designated'

is_agricultural = lambda x: x.get('motor_vehicle') in ['agricultural', 'forestry']
is_accessible = lambda x: pd.isnull(x['access']) or not is_not_accessible(x)
is_tram = lambda x: x['tram'] == 'yes'
is_smooth = lambda x: pd.isnull(x['tracktype']) or x['tracktype'] in ['grade1', 'grade2']
is_vehicle_allowed = lambda x: pd.isnull(x.get('motor_vehicle')) or x.get('motor_vehicle') != 'no'

is_service_tag = lambda x: x['highway'] in ['service']
is_service = lambda x: (is_service_tag(x) or (is_agricultural(x) and is_accessible(x)) or (is_path(x) and is_accessible(x)) or (is_track(x) and is_accessible(x) and is_smooth(x) and is_vehicle_allowed(x))) and (not is_designated(x))

can_cardrive = lambda x: x['highway'] in ['motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'unclassified', 'road', 'residential', 'living_street', 'primary_link', 'secondary_link', 'tertiary_link', 'motorway_link', 'trunk_link']
is_path_not_forbidden = lambda x: x['highway'] in ['cycleway', 'track', 'path'] and (not cannot_bike(x))

is_bikepath_right = lambda x: x.get('highway') in ['cycleway'] or (any((key for key, value in x.items() if 'right:bicycle' in key and value in ['designated'])) and (not any((key for key, value in x.items() if key == 'cycleway:right:lane')))) or x.get('cycleway') in ['track', 'sidepath', 'crossing'] or (x.get('cycleway:right') in ['track', 'sidepath', 'crossing']) or (x.get('cycleway:both') in ['track', 'sidepath', 'crossing']) or any((key for key, value in x.items() if 'right:traffic_sign' in key and value in ['237']))
is_bikepath_left = lambda x: x.get('highway') in ['cycleway'] or (any((key for key, value in x.items() if 'left:bicycle' in key and value in ['designated'])) and (not any((key for key, value in x.items() if key == 'cycleway:left:lane')))) or x.get('cycleway') in ['track', 'sidepath', 'crossing'] or (x.get('cycleway:left') in ['track', 'sidepath', 'crossing']) or (x.get('cycleway:both') in ['track', 'sidepath', 'crossing']) or any((key for key, value in x.items() if 'left:traffic_sign' in key and value in ['237']))

is_pedestrian_right = lambda x: is_footway(x) and (not can_bike(x)) and (not is_indoor(x)) or (is_path(x) and can_walk_right(x) and (not can_bike(x)) and (not is_indoor(x)))
is_pedestrian_left = lambda x: is_footway(x) and (not can_bike(x)) and (not is_indoor(x)) or (is_path(x) and can_walk_left(x) and (not can_bike(x)) and (not is_indoor(x)))

is_shared_with_mit_right = lambda x: x.get('cycleway') in ['shared_lane'] or x.get('cycleway:right') in ['shared_lane'] or x.get('cycleway:both') in ['shared_lane']
is_shared_with_mit_left = lambda x: x.get('cycleway') in ['shared_lane'] or x.get('cycleway:left') in ['shared_lane'] or x.get('cycleway:both') in ['shared_lane']

is_cycle_highway = lambda x: x.get('cycle_highway') == 'yes' or x.get('traffic_sign') == '350.1' or x.get('traffic_sign:forward') == '350.1'
is_bikeroad = lambda x: x.get('bicycle_road') == 'yes' or x.get('cyclestreet') == 'yes' or x.get('traffic_sign') in ['244.1', '244.3'] or (x.get('traffic_sign:forward') in ['244.1', '244.3'])
is_bikelane_right = lambda x: x.get('cycleway') in ['lane'] or x.get('cycleway:right') in ['lane'] or x.get('cycleway:both') in ['lane'] or any((key for key, value in x.items() if 'right:lane' in key and value in ['exclusive'])) or any((key for key, value in x.items() if 'right:traffic_sign' in key and value in ['237']))
is_bikelane_left = lambda x: x.get('cycleway') in ['lane'] or x.get('cycleway:left') in ['lane'] or x.get('cycleway:both') in ['lane'] or any((key for key, value in x.items() if 'left:lane' in key and value in ['exclusive'])) or any((key for key, value in x.items() if 'left:traffic_sign' in key and value in ['237']))
is_shared_buslane_right = lambda x: x.get('cycleway') == 'share_busway' or x.get('cycleway:right') == 'share_busway' or x.get('cycleway:both') == 'share_busway' or is_sign_shared_buslane(x)
is_shared_buslane_left = lambda x: x.get('cycleway') == 'share_busway' or x.get('cycleway:left') == 'share_busway' or x.get('cycleway:both') == 'share_busway' or is_sign_shared_buslane(x)

def _prepare_way(way_dict):
    if isinstance(way_dict, gpd.GeoDataFrame):
        if 'tags' in way_dict.columns:
            way_gdf = way_dict
            way_gdf['tags'] = way_gdf['tags'].apply(json.loads)
            way_gdf.reset_index(drop=True, inplace=True)
            way_n = pd.concat([way_gdf, pd.json_normalize(way_gdf['tags'])], axis=1)
            way_n = way_n[way_n.columns.intersection(OSM_KEYS)]
            way_dictionary = way_n.to_dict('records')
            return way_dictionary
        elif 'tag_string' in way_dict.columns:
            parse = []
            for index, row in way_dict.iterrows():
                pairs = row['tag_string'].split(',')
                row_data = {kv.split('=>')[0]: kv.split('=>')[1] for kv in pairs if '=>' in kv}
                parse.append(row_data)
            way_dataframe = pd.DataFrame(parse)
            dropcol = [col for col in OSM_KEYS if col in way_dataframe.columns]
            way_dataframe = way_dataframe[dropcol]
            way_dictionary = way_dataframe.to_dict('records')
            return way_dictionary
        else:
            raise ValueError('OSM dataframe must contain a tag column')
    elif isinstance(way_dict, dict):
        return {k: v for k, v in way_dict.items() if k in OSM_KEYS}
    else:
        raise TypeError('invalid format')

def _assess_directionality(way_gdf):
    way_gdf_exp = way_gdf.explode().reset_index().drop(columns=['level_0', 'level_1'])
    way_gdf_exp['start_point'] = way_gdf_exp['geometry'].apply(lambda x: list(x.coords)[0])
    way_gdf_exp['end_point'] = way_gdf_exp['geometry'].apply(lambda x: list(x.coords)[1])
    return way_gdf_exp

def set_value(x, single=False):
    if not isinstance(x, dict):
        raise TypeError('rowwise OSM data should be a dict')

    ## bicycle_way
    # First option: "bicycle_way"
    conditions_b_way_right = [
        is_bikepath_right(x) and not can_walk_right(x),  # 0 and 1
        is_bikepath_right(x) and is_segregated(x),  # 0 and 2
        can_bike(x) and (is_path(x) or is_track(x)) and not can_walk_right(x),
        # and not is_footway, #3, 4, 1
        can_bike(x) and (is_track(x) or is_footway(x) or is_path(x)) and is_segregated(x),
        # b_way_right_5 #3, 6, 2
        is_obligated_segregated(x),
        # and can_bike(x),  # 3,7 #ML here the idea was to remove the "can_bike" condition, due to redundancy
        is_bicycle_designated_right(x) and is_pedestrian_designated_right(x) and is_segregated(x)
    ]

    conditions_b_way_left = [
        is_bikepath_left(x) and not can_walk_left(x),  # 0 and 1
        is_bikepath_left(x) and is_segregated(x),  # 0 and 2
        can_bike(x) and (is_path(x) or is_track(x)) and not can_walk_left(x),
        # and not is_footway, #3, 4, 1
        can_bike(x) and (is_track(x) or is_footway(x) or is_path(x)) and is_segregated(x),
        # b_way_right_5 #3, 6, 2
        is_obligated_segregated(x),
        # and can_bike(x),  # 3,7 #ML here the idea was to remove the "can_bike" condition, due to redundancy
        is_bicycle_designated_left(x) and is_pedestrian_designated_left(x) and is_segregated(x)
    ]

    # Second option: "shared_way"
    ##shared
    conditions_shared_right = [
        is_bikepath_right(x) and can_walk_right(x) and not is_segregated(x),  # 0 and 1 and 2
        is_footway(x) and can_bike(x) and not is_segregated(x),  # 3 and 4 and 2
        (is_path(x) or is_track(x)) and can_bike(x) and can_walk_right(
            x) and not is_segregated(x),  # 5 and 4 and 1 and 2

        is_sign_shared_way(x),
        is_obligated_shared(x)
    ]
    conditions_shared_left = [
        is_bikepath_left(x) and can_walk_left(x) and not is_segregated(x),  # 0 and 1 and 2
        is_footway(x) and can_bike(x) and not is_segregated(x),  # 3 and 4 and 2
        (is_path(x) or is_track(x)) and can_bike(x) and can_walk_left(x) and not is_segregated(
            x),  # 5 and 4 and 1 and 2

        is_sign_shared_way(x),
        is_obligated_shared(x)
    ]

    # Add. Option: mit_road
    ##mit
    conditions_mit_right = [
        can_cardrive(x) and not is_bikepath_right(x) and not is_bikeroad(x) and not is_footway(
            x) and not is_bikelane_right(x) and not is_shared_buslane_right(x)
        and not is_path(x) and not is_track(x) and not cannot_bike(x),
        is_shared_with_mit_right(x)
        # ML can it be incorporated directly or should it be joined with other conditions? IMO it is self-sufficient.
    ]
    conditions_mit_left = [
        can_cardrive(x) and not is_bikepath_left(x) and not is_bikeroad(x) and not is_footway(
            x) and not is_bikelane_left(x) and not is_shared_buslane_left(x)
        and not is_path(x) and not is_track(x) and not cannot_bike(x),
        is_shared_with_mit_left(x)
    ]


    if not single:
        def get_infra(x):
            if 'access' in x.values() and is_not_accessible(x) or ('tram' in x.values() and is_tram(x)):
                return 'no'
            if is_cycle_highway(x):
                return 'cycle_highway'
            if is_bikeroad(x):
                return 'bicycle_road'
            if is_service(x):
                return 'service_misc'
            elif any(conditions_b_way_right):
                if any(conditions_b_way_left):
                    return 'bicycle_way_both'
                elif is_bikelane_left(x):
                    return 'bicycle_way_right_lane_left'
                elif is_shared_buslane_left(x):
                    return 'bicycle_way_right_bus_left'
                elif any(conditions_shared_left):
                    return 'bicycle_way_right_shared_left'
                elif any(conditions_mit_left):
                    return 'bicycle_way_right_mit_left'
                elif is_pedestrian_left(x):
                    return 'bicycle_way_right_pedestrian_left'
                else:
                    return 'bicycle_way_right_no_left'
            elif any(conditions_b_way_left):
                if is_bikelane_right(x):
                    return 'bicycle_way_left_lane_right'
                elif is_shared_buslane_right(x):
                    return 'bicycle_way_left_bus_right'
                elif any(conditions_shared_right):
                    return 'bicycle_way_left_shared_right'
                elif any(conditions_mit_right):
                    return 'bicycle_way_left_mit_right'
                elif is_pedestrian_right(x):
                    return 'bicycle_way_left_pedestrian_right'
                else:
                    return 'bicycle_way_left_no_right'
            elif is_bikelane_right(x):
                if is_bikelane_left(x):
                    return 'bicycle_lane_both'
                elif is_shared_buslane_left(x):
                    return 'bicycle_lane_right_bus_left'
                elif any(conditions_shared_left):
                    return 'bicycle_lane_right_shared_left'
                elif any(conditions_mit_left):
                    return 'bicycle_lane_right_mit_left'
                elif is_pedestrian_left(x):
                    return 'bicycle_lane_right_pedestrian_left'
                else:
                    return 'bicycle_lane_right_no_left'
            elif is_bikelane_left(x):
                if is_shared_buslane_right(x):
                    return 'bicycle_lane_left_bus_right'
                elif any(conditions_shared_right):
                    return 'bicycle_lane_left_shared_right'
                elif any(conditions_mit_right):
                    return 'bicycle_lane_left_mit_right'
                elif is_pedestrian_right(x):
                    return 'bicycle_lane_left_pedestrian_right'
                else:
                    return 'bicycle_lane_left_no_right'
            elif is_shared_buslane_right(x):
                if is_shared_buslane_left(x):
                    return 'bus_lane_both'
                elif any(conditions_shared_left):
                    return 'bus_lane_right_shared_left'
                elif any(conditions_mit_left):
                    return 'bus_lane_right_mit_left'
                elif is_pedestrian_left(x):
                    return 'bus_lane_right_pedestrian_left'
                else:
                    return 'bus_lane_right_no_left'
            elif is_shared_buslane_left(x):
                if any(conditions_shared_right):
                    return 'bus_lane_left_shared_right'
                elif any(conditions_mit_right):
                    return 'bus_lane_left_mit_right'
                elif is_pedestrian_right(x):
                    return 'bus_lane_left_pedestrian_right'
                else:
                    return 'bus_lane_left_no_right'
            elif any(conditions_shared_right):
                if any(conditions_shared_left):
                    return 'shared_way_both'
                elif any(conditions_mit_left):
                    return 'shared_way_right_mit_left'
                elif is_pedestrian_left(x):
                    return 'shared_way_right_pedestrian_left'
                else:
                    return 'shared_way_right_no_left'
            elif any(conditions_shared_left):
                if any(conditions_mit_right):
                    return 'shared_way_left_mit_right'
                elif is_pedestrian_right(x):
                    return 'shared_way_left_pedestrian_right'
                else:
                    return 'shared_way_left_no_right'
            elif any(conditions_mit_right):
                if any(conditions_mit_left):
                    return 'mit_road_both'
                elif is_pedestrian_left(x):
                    return 'mit_road_right_pedestrian_left'
                else:
                    return 'mit_road_right_no_left'
            elif any(conditions_mit_left):
                if is_pedestrian_right(x):
                    return 'mit_road_left_pedestrian_right'
                else:
                    return 'mit_road_left_no_right'
            elif is_pedestrian_right(x) and (not 'indoor' in x.values() or x['indoor'] != 'yes'):
                if is_pedestrian_left(x) and (not 'indoor' in x.values() or x['indoor'] != 'yes'):
                    if 'access' in x.values() and x['access'] == 'customers':
                        return 'no'
                    else:
                        return 'pedestrian_both'
                else:
                    return 'pedestrian_right_no_left'
            elif is_pedestrian_left(x) and (not 'indoor' in x.values() or x['indoor'] != 'yes'):
                if 'access' in x.values() and x['access'] == 'customers':
                    return 'no'
                else:
                    return 'pedestrian_left_no_right'
            elif is_path_not_forbidden(x):
                return 'path_not_forbidden'
            else:
                return 'no'
        cat = None
        cat = get_infra(x)
        assert isinstance(cat, str)
        return cat
    else:
        assert single

        def get_infra(x):
            if 'access' in x.values() and is_not_accessible(x) or ('tram' in x.values() and is_tram(x)):
                return 'no'
            if is_cycle_highway(x):
                return 'cycle_highway'
            if is_bikeroad(x):
                return 'bicycle_road'
            if is_service(x):
                return 'service_misc'
            elif any(conditions_b_way_left) or any(conditions_b_way_right):
                return 'bicycle_way'
            elif is_bikelane_left(x) or is_bikelane_right(x):
                return 'bicycle_lane'
            elif is_shared_buslane_left(x) or is_shared_buslane_right(x):
                return 'bus_lane'
            elif any(conditions_shared_left) or any(conditions_shared_right):
                return 'shared_way'
            elif any(conditions_mit_left) or any(conditions_mit_right):
                return 'mit_road'
            elif (is_pedestrian_left(x) or is_pedestrian_right(x)) and (not 'indoor' in x.values() or x['indoor'] != 'yes'):
                if 'access' in x.values() and x['access'] == 'customers':
                    return 'no'
                else:
                    return 'pedestrian'
            elif is_path_not_forbidden(x):
                return 'path_not_forbidden'
            else:
                return 'no'
        cat = None
        cat = get_infra(x)
        assert isinstance(cat, str)
        return cat

def _evaluate_indicators(x, in_cycling_relation=False):
    """
        Evaluate all indicator functions for a given way.
        Returns a dictionary of indicator names and their boolean values.
    """
    indicators = {
        # Basic infrastructure types
        'is_path': is_path(x),
        'is_footway': is_footway(x),
        'is_track': is_track(x),

        # Physical attributes
        'is_segregated': is_segregated(x),

        # Access/permissions
        'can_bike': can_bike(x),
        'can_walk_right': can_walk_right(x),
        'can_walk_left': can_walk_left(x),

        # Designation
        'is_designated': is_designated(x),
        'is_bicycle_designated_left': is_bicycle_designated_left(x),
        'is_bicycle_designated_right': is_bicycle_designated_right(x),
        'is_pedestrian_designated_left': is_pedestrian_designated_left(x),
        'is_pedestrian_designated_right': is_pedestrian_designated_right(x),

        # Traffic signs
        'is_obligated_segregated': is_obligated_segregated(x),
        'is_obligated_shared': is_obligated_shared(x),
        'is_sign_shared_way': is_sign_shared_way(x),
        'is_sign_shared_buslane': is_sign_shared_buslane(x),

        # Infrastructure presence (left/right)
        'is_bikepath_right': is_bikepath_right(x),
        'is_bikepath_left': is_bikepath_left(x),
        'is_bikelane_right': is_bikelane_right(x),
        'is_bikelane_left': is_bikelane_left(x),
        'is_shared_buslane_right': is_shared_buslane_right(x),
        'is_shared_buslane_left': is_shared_buslane_left(x),

        # Special categories
        'is_cycle_highway': is_cycle_highway(x),
        'is_bikeroad': is_bikeroad(x),

        # Relation membership
        'is_in_cycling_relation': in_cycling_relation
    }

    return indicators

def aggregate_the_no_infra_category(cat):
    options = {"service_misc": "no",

               "bicycle_way_right_mit_left": "bicycle_way_right_no_left",
               "bicycle_way_right_pedestrian_left": "bicycle_way_right_no_left",
               "bicycle_way_left_mit_right": "bicycle_way_left_no_right",
               "bicycle_way_left_pedestrian_right": "bicycle_way_left_no_right",

               "bicycle_lane_right_mit_left": "bicycle_lane_right_no_left",
               "bicycle_lane_right_pedestrian_left": "bicycle_lane_right_no_left",
               "bicycle_lane_left_mit_right": "bicycle_lane_left_no_right",
               "bicycle_lane_left_pedestrian_right": "bicycle_lane_left_no_right",

               "bus_lane_right_mit_left": "bus_lane_right_no_left",
               "bus_lane_right_pedestrian_left": "bus_lane_right_no_left",
               "bus_lane_left_mit_right": "bus_lane_left_no_right",
               "bus_lane_left_pedestrian_right": "bus_lane_left_no_right",

               "shared_way_right_mit_left": "shared_way_right_no_left",
               "shared_way_right_pedestrian_left": "shared_way_right_no_left",
               "shared_way_left_mit_right": "shared_way_left_no_right",
               "shared_way_left_pedestrian_right": "shared_way_left_no_right",

               "mit_road_both": "no",
               "mit_road_right_pedestrian_left": "no",
               "mit_road_right_no_left": "no",
               "mit_road_left_pedestrian_right": "no",
               "mit_road_left_no_right": "no",

               "pedestrian_both": "no",
               "pedestrian_right_no_left": "no",
               "pedestrian_left_no_right": "no",

               "path_not_forbidden": "no",

               # remaining single categories
               "mit_road": "no",
               "pedestrian": "no"
               }

    return options[cat] if cat in options.keys() else cat

def _export_to_pbf(input_pbf, osm_df):
    """
        Export classification results to a new PBF file by adding bicycle_infrastructure tag to ways.
        """
    output_pbf = 'bikeneat_' + input_pbf
    try:
        import osmium
        way_to_infra = dict(zip(osm_df['id'], osm_df['bicycle_infrastructure']))

        class TagWriter(osmium.SimpleHandler):

            def __init__(self, writer, way_to_infra):
                super().__init__()
                self.writer = writer
                self.way_to_infra = way_to_infra

            def node(self, n):
                self.writer.add_node(n)

            def way(self, w):
                if w.id in self.way_to_infra:
                    wb = osmium.osm.mutable.Way(w)
                    wb.tags = list(w.tags) + [('bicycle_infrastructure', self.way_to_infra[w.id])]
                    self.writer.add_way(wb)
                else:
                    self.writer.add_way(w)

            def relation(self, r):
                self.writer.add_relation(r)
        writer = osmium.SimpleWriter(output_pbf)
        handler = TagWriter(writer, way_to_infra)
        handler.apply_file(input_pbf, locations=True, idx='flex_mem')
        writer.close()
        print(f'Exported {len(way_to_infra)} ways with bicycle_infrastructure tags to {output_pbf}')
    except Exception as e:
        print(f'Warning: Could not export to PBF: {str(e)}')


def classify_with_bikeneat(pbf_path, single=False, aggregated=True, output_arg={}):
    try:

        osm_file = pyrosm.OSM(pbf_path)  # hier laden wir die protobuf

        osm_bike = osm_file.get_network(
            network_type="cycling")  # hier wird die protobuf in eine dataframe umgewnandelt für das profil fahrrad
        osm_drive = osm_file.get_network(
            network_type="driving")  # hier wird die protobuf in eine dataframe umgewnandelt für das profil auto

        # preprocessing für beide dataframes, da beim mergen zwangsläufig spalten mit 'nan' entstehen
        osm = pd.merge(left=osm_bike, right=osm_drive, how='outer', on='id')
        osm = osm.loc[:, ~osm.columns.str.endswith('_y')]
        osm.columns = osm.columns.str.rstrip('_x')

        osm_mask = ['id', 'osm_type', 'geometry', 'area']
        mask = osm.drop(columns=osm_mask).notna().any(axis=1)
        osm_df = osm[mask]

        # Extract cycling relation membership from PBF file if provided
        cycling_way_ids = set()

        try:
            import osmium

            class RelationMemberHandler(osmium.SimpleHandler):
                def __init__(self):
                    super().__init__()
                    self.cycling_way_ids = set()

                def relation(self, r):
                    tags = {t.k: t.v for t in r.tags}
                    is_cycling = (
                            tags.get('route') == 'bicycle' or
                            tags.get('network') in ['lcn', 'rcn', 'ncn', 'icn'] or
                            tags.get('bicycle') in ['yes', 'designated']
                    )
                    if is_cycling:
                        for member in r.members:
                            if member.type == 'w':
                                self.cycling_way_ids.add(member.ref)

            handler = RelationMemberHandler()
            handler.apply_file(pbf_path)
            cycling_way_ids = handler.cycling_way_ids

        except Exception as e:
            print(f"Warning: Could not load relation data: {str(e)}")
            cycling_way_ids = set()

        # Build lookup dict from way ID to relation membership
        way_id_to_relation = {}
        if cycling_way_ids and 'id' in osm_df.columns:
            way_id_to_relation = {way_id: (way_id in cycling_way_ids) for way_id in osm_df['id']}

        prepared_data = _prepare_way(osm_df)

        osm_infra = []
        indicators_data = [] if output_arg.get("include_indicators", False) else None

        for idx, kante in enumerate(tqdm(prepared_data, total=len(prepared_data))):
            result = set_value(kante, single=single)

            if aggregated:
                result = aggregate_the_no_infra_category(result)

            osm_infra.append(result)

            # Evaluate and store all indicators if requested
            if output_arg.get("include_indicators", False):
                # Get way ID and check relation membership
                way_id = osm_df.iloc[idx]['id'] if 'id' in osm_df.columns else None
                in_relation = way_id_to_relation.get(way_id, False) if way_id else False
                indicators = _evaluate_indicators(kante, in_cycling_relation=in_relation)
                indicators_data.append(indicators)

        # osm_df = osm_df.explode()
        osm_df['bicycle_infrastructure'] = osm_infra

        # Add indicator columns if requested
        if output_arg.get("include_indicators", False) and indicators_data:
            indicators_df = pd.DataFrame(indicators_data)
            # Add all indicator columns to the output dataframe
            for col in indicators_df.columns:
                osm_df[col] = indicators_df[col].values

        # Export to PBF if requested
        if output_arg.get("export_pbf", False) and 'id' in osm_df.columns:
            _export_to_pbf(pbf_path, osm_df)

        return osm_df

    except Exception as e:
        print(f"An error occurred during classification: {str(e)}")
        return None
