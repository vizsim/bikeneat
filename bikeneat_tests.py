import importlib.util
import sys
import types
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import LineString


MODULE_PATH = "bikeneat_functions.py"


@pytest.fixture()
def bikeneat(monkeypatch):
    # Make the import independent of whether pyrosm is installed in the test environment.
    fake_pyrosm = types.SimpleNamespace(OSM=None)
    monkeypatch.setitem(sys.modules, "pyrosm", fake_pyrosm)

    spec = importlib.util.spec_from_file_location("bikeneat_functions", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["bikeneat_functions"] = module
    spec.loader.exec_module(module)
    return module


class FakeOSM:
    def __init__(self, pbf_path):
        self.pbf_path = pbf_path

    def get_network(self, network_type):
        tags_by_id = {
            1: {"highway": "cycleway"},
            2: {"highway": "residential", "cycleway:right": "lane"},
            3: {"highway": "residential", "bicycle_road": "yes"},
            4: {"highway": "path", "bicycle": "yes", "foot": "yes"},
            5: {"highway": "service"},
        }
        rows = []
        if network_type == "cycling":
            ids = [1, 2, 3, 4, 5]
        elif network_type == "driving":
            ids = [2, 3, 5]
        else:
            raise ValueError(network_type)

        module = sys.modules["bikeneat_functions"]
        for way_id in ids:
            complete_tags = {key: None for key in module.OSM_KEYS}
            complete_tags.update(tags_by_id[way_id])
            rows.append(
                {
                    "id": way_id,
                    "osm_type": "way",
                    "area": None,
                    "tags": __import__("json").dumps(complete_tags),
                    "geometry": LineString([(0, 0), (1, 0)]),
                }
            )

        return gpd.GeoDataFrame(rows, geometry="geometry")


def test_classify_default_output_has_classification_column(bikeneat, monkeypatch):
    monkeypatch.setattr(bikeneat.pyrosm, "OSM", FakeOSM)

    result = bikeneat.classify_with_bikeneat("Wedel_highway.osm.pbf")

    assert result is not None
    assert "bicycle_infrastructure" in result.columns
    assert len(result) == 5


def test_prepare_way_tolerates_missing_tags(bikeneat):
    # pyrosm leaves 'tags' as NaN for ways that carry no tags beyond the standard
    # columns; json.loads must not be applied to those.
    gdf = gpd.GeoDataFrame(
        [
            {"id": 1, "tags": '{"highway":"cycleway"}',
             "geometry": LineString([(0, 0), (1, 0)])},
            {"id": 2, "tags": float("nan"),
             "geometry": LineString([(0, 0), (1, 0)])},
        ],
        geometry="geometry",
    )

    prepared = bikeneat._prepare_way(gdf)

    assert len(prepared) == 2
    assert prepared[0]["highway"] == "cycleway"
    # the untagged way must still classify, and as no infrastructure
    assert bikeneat.set_value(prepared[1], single=True) == "no"


def test_classify_single_true_returns_single_categories(bikeneat, monkeypatch):
    monkeypatch.setattr(bikeneat.pyrosm, "OSM", FakeOSM)

    result = bikeneat.classify_with_bikeneat("Wedel_highway.osm.pbf", single=True)
    by_id = result.set_index("id")["bicycle_infrastructure"].to_dict()

    assert by_id[1] == "bicycle_way"
    assert by_id[2] == "bicycle_lane"
    assert by_id[3] == "bicycle_road"


def test_classify_single_false_returns_directional_categories(bikeneat, monkeypatch):
    monkeypatch.setattr(bikeneat.pyrosm, "OSM", FakeOSM)

    result = bikeneat.classify_with_bikeneat("Wedel_highway.osm.pbf", single=False)
    by_id = result.set_index("id")["bicycle_infrastructure"].to_dict()

    assert by_id[1] == "bicycle_way_both"
    assert by_id[2] == "bicycle_lane_right_no_left"


def test_classify_aggregated_false_keeps_no_infra_subcategories(bikeneat, monkeypatch):
    monkeypatch.setattr(bikeneat.pyrosm, "OSM", FakeOSM)

    result = bikeneat.classify_with_bikeneat("Wedel_highway.osm.pbf", single=True, aggregated=False)
    by_id = result.set_index("id")["bicycle_infrastructure"].to_dict()

    assert by_id[5] == "service_misc"


def test_classify_aggregated_true_collapses_no_infra_subcategories(bikeneat, monkeypatch):
    monkeypatch.setattr(bikeneat.pyrosm, "OSM", FakeOSM)

    result = bikeneat.classify_with_bikeneat("Wedel_highway.osm.pbf", single=True, aggregated=True)
    by_id = result.set_index("id")["bicycle_infrastructure"].to_dict()

    assert by_id[5] == "no"


def test_classify_include_indicators_adds_indicator_columns(bikeneat, monkeypatch):
    monkeypatch.setattr(bikeneat.pyrosm, "OSM", FakeOSM)

    result = bikeneat.classify_with_bikeneat(
        "Wedel_highway.osm.pbf",
        single=True,
        output_arg={"include_indicators": True},
    )

    assert "is_bikepath_right" in result.columns
    assert "is_bikelane_right" in result.columns
    assert "is_in_cycling_relation" in result.columns
    assert result.loc[result["id"] == 1, "is_bikepath_right"].iloc[0] == True



def test_output_arg_empty_dict_does_not_add_indicator_columns(bikeneat, monkeypatch):
    monkeypatch.setattr(bikeneat.pyrosm, "OSM", FakeOSM)

    result = bikeneat.classify_with_bikeneat(
        "Wedel_highway.osm.pbf",
        output_arg={},
    )

    assert result is not None
    assert "bicycle_infrastructure" in result.columns
    assert "is_bikepath_right" not in result.columns
    assert "is_in_cycling_relation" not in result.columns


def test_output_arg_include_indicators_false_does_not_add_indicator_columns(bikeneat, monkeypatch):
    monkeypatch.setattr(bikeneat.pyrosm, "OSM", FakeOSM)

    result = bikeneat.classify_with_bikeneat(
        "Wedel_highway.osm.pbf",
        output_arg={"include_indicators": False},
    )

    assert result is not None
    assert "bicycle_infrastructure" in result.columns
    assert "is_bikepath_right" not in result.columns
    assert "is_bikelane_right" not in result.columns
    assert "is_in_cycling_relation" not in result.columns


def test_output_arg_unknown_keys_are_ignored(bikeneat, monkeypatch):
    monkeypatch.setattr(bikeneat.pyrosm, "OSM", FakeOSM)

    result = bikeneat.classify_with_bikeneat(
        "Wedel_highway.osm.pbf",
        output_arg={"unknown_option": True},
    )

    assert result is not None
    assert "bicycle_infrastructure" in result.columns
    assert "is_bikepath_right" not in result.columns


def test_output_arg_export_pbf_false_does_not_call_export(bikeneat, monkeypatch):
    monkeypatch.setattr(bikeneat.pyrosm, "OSM", FakeOSM)

    export_calls = []

    def fake_export(input_pbf, osm_df, output_dir=None):
        export_calls.append((input_pbf, osm_df))

    monkeypatch.setattr(bikeneat, "_export_to_pbf", fake_export)

    result = bikeneat.classify_with_bikeneat(
        "Wedel_highway.osm.pbf",
        output_arg={"export_pbf": False},
    )

    assert result is not None
    assert export_calls == []


def test_output_arg_export_pbf_true_calls_export_with_result_dataframe(bikeneat, monkeypatch):
    monkeypatch.setattr(bikeneat.pyrosm, "OSM", FakeOSM)

    export_calls = []

    def fake_export(input_pbf, osm_df, output_dir=None):
        export_calls.append((input_pbf, osm_df.copy()))

    monkeypatch.setattr(bikeneat, "_export_to_pbf", fake_export)

    result = bikeneat.classify_with_bikeneat(
        "Wedel_highway.osm.pbf",
        output_arg={"export_pbf": True},
    )

    assert result is not None
    assert len(export_calls) == 1
    exported_pbf, exported_df = export_calls[0]
    assert exported_pbf == "Wedel_highway.osm.pbf"
    assert "bicycle_infrastructure" in exported_df.columns
    assert len(exported_df) == len(result)


def test_output_arg_include_indicators_and_export_pbf_together(bikeneat, monkeypatch):
    monkeypatch.setattr(bikeneat.pyrosm, "OSM", FakeOSM)

    export_calls = []

    def fake_export(input_pbf, osm_df, output_dir=None):
        export_calls.append((input_pbf, osm_df.copy()))

    monkeypatch.setattr(bikeneat, "_export_to_pbf", fake_export)

    result = bikeneat.classify_with_bikeneat(
        "Wedel_highway.osm.pbf",
        output_arg={"include_indicators": True, "export_pbf": True},
    )

    assert result is not None
    assert len(export_calls) == 1
    exported_df = export_calls[0][1]
    assert "bicycle_infrastructure" in exported_df.columns
    assert "is_bikepath_right" in exported_df.columns
    assert "is_in_cycling_relation" in exported_df.columns


def test_output_arg_include_indicators_false_and_export_pbf_true(bikeneat, monkeypatch):
    monkeypatch.setattr(bikeneat.pyrosm, "OSM", FakeOSM)

    export_calls = []

    def fake_export(input_pbf, osm_df, output_dir=None):
        export_calls.append((input_pbf, osm_df.copy()))

    monkeypatch.setattr(bikeneat, "_export_to_pbf", fake_export)

    result = bikeneat.classify_with_bikeneat(
        "Wedel_highway.osm.pbf",
        output_arg={"include_indicators": False, "export_pbf": True},
    )

    assert result is not None
    assert len(export_calls) == 1
    exported_df = export_calls[0][1]
    assert "bicycle_infrastructure" in exported_df.columns
    assert "is_bikepath_right" not in exported_df.columns
    assert "is_in_cycling_relation" not in exported_df.columns
