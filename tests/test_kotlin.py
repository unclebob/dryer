from dryer.extract import entries_in_source
from dryer.shape import jaccard


def spans(source: str) -> list[tuple[int, int]]:
    entries, warning = entries_in_source("kotlin", source, "Demo.kt", "Demo.kt")
    assert warning is None
    return [(entry.start_line, entry.end_line) for entry in entries]


def test_top_level_member_and_interface_functions_with_a_body_are_units():
    source = """\
fun top(x: Int): Int {
    return x
}

class Box {
    fun member(x: Int) = x + 1
}

interface Shape {
    fun area(): Int
    fun twice(): Int { return area() * 2 }
}
"""
    assert spans(source) == [(1, 3), (6, 6), (11, 11)]


def test_a_function_without_a_body_is_not_a_unit():
    source = """\
interface Shape {
    fun area(): Int
}

abstract class Base {
    abstract fun name(): String
}

fun kept() = 1
"""
    assert spans(source) == [(9, 9)]


def test_a_secondary_constructor_with_a_body_is_a_unit():
    source = """\
class Box(val a: Int) {
    constructor(a: String) : this(a.length) {
        println(a)
    }
}
"""
    assert spans(source) == [(2, 4)]


def test_a_constructor_that_only_delegates_is_not_a_unit():
    source = """\
class Box(val a: Int) {
    constructor() : this(0)
    constructor(a: String) : this(a.length)
    fun kept() = 1
}
"""
    assert spans(source) == [(4, 4)]


def test_getters_and_setters_with_a_body_are_units():
    source = """\
class Box {
    var size: Int = 0
        get() = field
        set(value) {
            field = value
        }
    val plain: Int = 1
}
"""
    assert spans(source) == [(3, 3), (4, 6)]


def test_functions_nested_in_a_unit_are_not_their_own_units():
    source = """\
fun outer(xs: List<Int>): Int {
    fun local(p: Int) = p + 1
    val job = object : Runnable {
        override fun run() { local(1) }
    }
    val anon = fun(a: Int): Int { return a }
    xs.forEach { x ->
        println(x)
    }
    return xs.size
}
"""
    assert spans(source) == [(1, 11)]


def test_members_of_an_object_declared_inside_a_class_are_units():
    source = """\
class Box {
    companion object {
        fun make() = Box()
    }
}
"""
    assert spans(source) == [(3, 3)]


def test_a_getter_inside_a_property_initialised_by_a_lambda_is_not_a_unit():
    source = """\
val handler = Handler { value: Int ->
    object : Holder {
        val size: Int get() = value
    }
}

fun kept() = 1
"""
    assert spans(source) == [(7, 7)]


def score(left: str, right: str) -> float:
    """Jaccard score of the only unit in each source, as dryer reports it."""

    found = []
    for source in (left, right):
        entries, _ = entries_in_source("kotlin", source, "Demo.kt", "Demo.kt")
        assert len(entries) == 1
        found.append(entries[0].fingerprints)
    return jaccard(found[0], found[1])


def test_renamed_locals_parameters_and_types_score_one():
    left = """\
fun alpha(xs: List<Int>): List<Int> {
    val ys = filter(xs, odd)
    return map(ys, inc)
}
"""
    right = """\
fun beta(items: Set<String>): Set<String> {
    val kept = filter(items, even)
    return map(kept, dec)
}
"""
    assert score(left, right) == 1.0


def test_a_different_called_function_lowers_the_score():
    left = "fun alpha(xs: Int): Int {\n    val ys = filter(xs)\n    return map(ys)\n}\n"
    right = "fun beta(xs: Int): Int {\n    val ys = filter(xs)\n    return reduce(ys)\n}\n"
    assert score(left, right) < 1.0


def test_a_called_method_name_stays_and_a_property_name_does_not():
    left = "fun alpha(a: Order): Int {\n    return a.items.count(a.total)\n}\n"
    same = "fun beta(b: Row): Int {\n    return b.rows.count(b.amount)\n}\n"
    other = "fun gamma(b: Row): Int {\n    return b.rows.sum(b.amount)\n}\n"
    assert score(left, same) == 1.0
    assert score(left, other) < 1.0


def test_structurally_different_functions_score_low():
    left = """\
fun alpha(xs: List<Int>): Int {
    var total = 0
    for (x in xs) {
        total += weigh(x)
    }
    return total
}
"""
    right = """\
fun beta(name: String): String {
    log(name)
    return name.trim()
}
"""
    assert score(left, right) < 0.5
