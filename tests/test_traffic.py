import pytest

from samfunnsdata import network
from samfunnsdata.query_plan import (
    QueryPlan,
    execute_query_plan,
    plan_from_traffic_question,
    validate_query_plan,
)
from samfunnsdata.questions import TrafficQuestion, parse_question


def test_traffic_question_parsing():
    assert parse_question("Hvor mye trafikk er det på E6?") == TrafficQuestion("E6", "latest", None)
    assert parse_question("Vis trafikkutviklingen på E6 siden 2015") == TrafficQuestion("E6", "history", 2015)
    assert parse_question("Hva er ÅDT på E39?") == TrafficQuestion("E39", "latest", None)


def test_traffic_query_plan_round_trip_and_validation():
    plan = plan_from_traffic_question(TrafficQuestion("E6", "history", 2015))
    assert validate_query_plan(QueryPlan.from_json(plan.to_json())) == plan
    assert plan.plan_hash() == QueryPlan.from_json(plan.to_json()).plan_hash()


def test_traffic_cache_only_zero_network():
    network.set_mode(network.NetworkMode.CACHE_ONLY)
    try:
        with pytest.raises(network.CacheOnlyMiss):
            execute_query_plan(plan_from_traffic_question(TrafficQuestion("E6", "latest", None)))
    finally:
        network.set_mode(network.NetworkMode.ONLINE)
