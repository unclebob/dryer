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


BODY = "    val ys = filter(xs)\n    return map(ys)\n"


def test_modifiers_do_not_change_the_structure():
    plain = f"fun alpha(xs: Int): Int {{\n{BODY}}}\n"
    modified = (
        "class Box {\n"
        f"    private suspend inline override fun beta(xs: Int): Int {{\n{BODY}    }}\n"
        "}\n"
    )
    assert score(plain, modified) == 1.0


def test_annotations_on_the_function_and_its_parameters_are_dropped():
    plain = f"fun alpha(xs: Int): Int {{\n{BODY}}}\n"
    annotated = f'@Suppress("unused") @Throws(Exception::class)\nfun beta(@Body xs: Int): Int {{\n{BODY}}}\n'
    assert score(plain, annotated) == 1.0


def test_an_annotation_on_a_local_property_is_dropped():
    plain = "fun alpha(xs: Int): Int {\n    val ys = filter(xs)\n    return map(ys)\n}\n"
    annotated = "fun beta(xs: Int): Int {\n    @Suppress(\"x\") val ys = filter(xs)\n    return map(ys)\n}\n"
    assert score(plain, annotated) == 1.0


def test_a_java_modifier_still_counts_in_java():
    plain = "class A {\n  int a(int x) {\n    return f(x);\n  }\n}\n"
    marked = "class A {\n  @Override\n  public int a(int x) {\n    return f(x);\n  }\n}\n"
    found = [entries_in_source("java", src, "A.java", "A.java")[0][0] for src in (plain, marked)]
    assert jaccard(found[0].fingerprints, found[1].fingerprints) < 1.0


def _returning(expression: str) -> str:
    return f"fun f(a: Int): Int {{\n    val x = {expression}\n    return use(x)\n}}\n"


def test_every_kind_of_literal_is_one_literal_node():
    base = _returning("1")
    for literal in ["2L", "0xFF", "0b101", "1.5", "2.5f", "7u", "'c'", "true", "null", '"text"']:
        assert score(base, _returning(literal)) == 1.0, literal


def test_a_string_template_is_one_literal_node():
    base = _returning('"plain"')
    assert score(base, _returning('"a $b ${c + d} e"')) == 1.0
    assert score(base, _returning('"""raw $b"""')) == 1.0


def test_a_literal_is_not_a_name():
    assert score(_returning("1"), _returning("other")) < 1.0


def _call(arguments: str) -> str:
    return f"fun f(a: Int): Int {{\n    val x = make({arguments})\n    return use(x)\n}}\n"


def test_a_named_argument_label_is_dropped():
    assert score(_call("1, 2"), _call("first = 1, second = 2")) == 1.0
    assert score(_call("1, 2"), _call("second = 1, first = 2")) == 1.0


def test_a_named_argument_keeps_its_value_structure():
    assert score(_call("one(1)"), _call("n = one(1)")) == 1.0
    assert score(_call("one(1)"), _call("n = other(1)")) < 1.0


def test_an_argument_count_still_counts():
    assert score(_call("1, 2"), _call("n = 1")) < 1.0


def _statement(call: str) -> str:
    return f"fun f(a: Int): Int {{\n    {call}\n    return use(a)\n}}\n"


def test_a_trailing_lambda_has_the_shape_of_a_parenthesised_one():
    shapes = ["run { a }", "run() { a }", "run({ a })"]
    for left in shapes:
        for right in shapes:
            assert score(_statement(left), _statement(right)) == 1.0, (left, right)


def test_a_trailing_lambda_after_arguments_matches_a_last_argument_lambda():
    assert score(_statement("run(a) { a }"), _statement("run(a, { a })")) == 1.0
    assert score(_statement("a.run(1, 2) { a }"), _statement("a.run(1, 2, { a })")) == 1.0


def test_the_argument_before_a_lambda_still_counts():
    assert score(_statement("run(a) { a }"), _statement("run { a }")) < 1.0
    assert score(_statement("run { a }"), _statement("run({ a }, { a })")) < 1.0
