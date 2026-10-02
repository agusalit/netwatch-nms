from app.routes.devices import _sparkline_points


def test_empty_list_returns_empty_string():
    assert _sparkline_points([]) == ""


def test_single_value_returns_empty_string():
    assert _sparkline_points([5.0]) == ""


def test_two_values_returns_two_points():
    result = _sparkline_points([1.0, 2.0])
    assert result != ""
    assert len(result.split(" ")) == 2


def test_identical_values_does_not_divide_by_zero():

    result = _sparkline_points([5.0, 5.0, 5.0])
    assert result != ""
    assert len(result.split(" ")) == 3