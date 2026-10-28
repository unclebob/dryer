from dryer.discover import language_of
from dryer.extract import entries_in_source
from dryer.model import Entry
from dryer.scan import find_duplicates


def forms(language: str, source: str, file: str) -> list[Entry]:
    entries, warning = entries_in_source(language, source, file, file)
    assert warning is None
    return entries


def score(language: str, left: str, right: str) -> float:
    suffix = {"kotlin": "kt", "java": "java", "python": "py"}[language]
    entries = forms(language, left, f"a.{suffix}") + forms(language, right, f"b.{suffix}")
    found = find_duplicates(entries, threshold=0.0)
    assert len(found) == 1
    return found[0].score


def spans(source: str) -> list[tuple[int, int]]:
    return [(entry.start_line, entry.end_line) for entry in forms("kotlin", source, "a.kt")]


SAVE = """\
fun saveUser(repo: Repo, user: User): Boolean {
    val ok = repo.validate(user)
    if (ok) repo.insert(user)
    return audit.record(user)
}
"""

DROP = """\
fun dropUser(repo: Repo, user: User): Boolean {
    val ok = repo.authorize(user)
    if (ok) repo.delete(user)
    return mailer.notify(user)
}
"""

JAVA_SAVE = """\
class A {
  boolean saveUser(Repo repo, User user) {
    boolean ok = repo.validate(user);
    if (ok) repo.insert(user);
    return audit.record(user);
  }
}
"""

JAVA_DROP = """\
class B {
  boolean dropUser(Repo repo, User user) {
    boolean ok = repo.authorize(user);
    if (ok) repo.delete(user);
    return mailer.notify(user);
  }
}
"""


def test_kt_is_kotlin():
    assert language_of("src/main/kotlin/App.kt") == "kotlin"
    assert language_of("build.gradle.kts") is None


def test_renamed_locals_and_literals_score_one():
    renamed = """\
fun keepUser(store: Repo, who: User): Boolean {
    val good = store.validate(who)
    if (good) store.insert(who)
    return audit.record(who, 0xFF)
}
"""
    literal = SAVE.replace("record(user)", "record(user, 2.5)")
    assert score("kotlin", literal, renamed) == 1.0


def test_different_callees_score_about_what_java_does():
    kotlin = score("kotlin", SAVE, DROP)
    java = score("java", JAVA_SAVE, JAVA_DROP)
    assert kotlin < 0.5
    assert abs(kotlin - java) < 0.1


def test_a_navigation_call_keeps_the_method_name():
    fingerprints = " ".join(forms("kotlin", SAVE, "a.kt")[0].fingerprints)
    assert '"validate"' in fingerprints
    assert '"record"' in fingerprints
    assert '"repo"' not in fingerprints
    assert '"user"' not in fingerprints


def test_a_field_name_is_not_part_of_the_structure():
    left = "fun alpha(order: Order): Int {\n    return order.total\n}\n"
    right = "fun beta(row: Row): Int {\n    return row.amount\n}\n"
    assert score("kotlin", left, right) == 1.0


def test_a_safe_call_is_not_a_plain_call():
    plain = "fun alpha(xs: List) {\n    xs.clear()\n}\n"
    safe = "fun beta(xs: List?) {\n    xs?.clear()\n}\n"
    assert score("kotlin", plain, safe) < 1.0


def test_kotlin_operators_stay():
    left = "fun alpha(x: Any, y: Set) = x is String"
    right = "fun beta(x: Any, y: Set) = x in y"
    assert score("kotlin", left, right) < 1.0
    cast = "fun alpha(x: Any) = x as String"
    safe_cast = "fun beta(x: Any) = x as? String"
    assert score("kotlin", cast, safe_cast) < 1.0


def test_python_in_and_is_are_not_kotlin_operators():
    left = "def alpha(x, y):\n    return x in y\n"
    right = "def beta(x, y):\n    return x is y\n"
    assert score("python", left, right) == 1.0


def test_an_interpolated_string_is_not_a_plain_literal():
    plain = 'fun alpha(name: String) = greet("hello")'
    interpolated = 'fun beta(name: String) = greet("hello $name")'
    assert score("kotlin", plain, interpolated) < 1.0


def test_every_fun_with_a_body_is_a_candidate():
    assert spans(
        """\
fun top(): Int = 1

fun String.shout(): String {
    return uppercase()
}

class Board {
    fun alpha(): Int {
        return 1
    }
    companion object {
        fun beta() = 2
    }
}

object Registry {
    fun gamma() {}
}

enum class Shape {
    SQUARE {
        override fun sides() = 4
    };
    abstract fun sides(): Int
}
"""
    ) == [(1, 1), (3, 5), (8, 10), (12, 12), (17, 17), (22, 22)]


def test_local_functions_lambdas_and_anonymous_objects_stay_inside():
    assert spans(
        """\
interface Runner {
    fun declared()
}

fun outer() {
    fun local() {}
    val f = fun() {}
    val g = { x: Int -> x }
    val r = object : Runner {
        override fun declared() {}
    }
    class Local {
        fun method() {}
    }
}
"""
    ) == [(5, 15)]


def test_a_comment_between_a_call_and_a_parenthesized_line_is_read():
    source = """\
fun alpha(a: A) {
    a.run { x }
    // note
    (a.b as? C)?.d()
}
"""
    entries = forms("kotlin", source, "a.kt")
    assert [(entry.start_line, entry.end_line) for entry in entries] == [(1, 5)]
    assert any('"run"' in item for item in entries[0].fingerprints)


def test_an_infix_call_keeps_its_name():
    until = "fun alpha(n: Int): List<Int> {\n    return (0 until 3).toList()\n}\n"
    down_to = "fun beta(n: Int): List<Int> {\n    return (0 downTo 3).toList()\n}\n"
    other_bounds = "fun beta(n: Int): List<Int> {\n    return (1 until 2).toList()\n}\n"
    assert any('"until"' in item for item in forms("kotlin", until, "a.kt")[0].fingerprints)
    assert score("kotlin", until, down_to) < 1.0
    assert score("kotlin", until, other_bounds) == 1.0


def test_infix_operands_are_not_names():
    left = "fun alpha(a: Int, b: Int) = a shl b"
    right = "fun beta(x: Int, y: Int) = x shl y"
    assert score("kotlin", left, right) == 1.0


INLINE_PAIR = """\
inline fun alpha(xs: List<Int>): List<Int> {
    val ys = xs.filter { it > 0 }
    return ys.map { it + 1 }
}

inline fun beta(items: List<Int>): List<Int> {
    val kept = items.filter { it > 0 }
    return kept.map { it + 1 }
}
"""


def test_identical_inline_functions_are_not_compared():
    assert find_duplicates(forms("kotlin", INLINE_PAIR, "a.kt"), threshold=0.0) == []


def test_the_same_functions_without_inline_score_one():
    plain = INLINE_PAIR.replace("inline fun", "fun")
    found = find_duplicates(forms("kotlin", plain, "a.kt"), threshold=0.0)
    assert [item.score for item in found] == [1.0]


def test_every_placement_of_inline_is_skipped():
    assert spans(
        """\
inline fun a() {}
public inline fun b() {}
internal inline fun c() {}
private inline fun d() {}
@InlineOnly inline fun e() {}
inline fun <reified T> f() {}
inline fun String.g() {}
class Board {
    inline fun h() {}
    override inline fun i() {}
    companion object {
        inline fun j() {}
    }
}
object Registry {
    inline fun k() {}
}
fun kept() {}
"""
    ) == [(18, 18)]


def test_methods_of_a_value_class_or_inline_class_are_compared():
    assert spans(
        """\
@JvmInline
value class Meters(val value: Int) {
    fun twice() = value * 2
}
inline class Feet(val value: Int) {
    fun twice() = value * 2
}
"""
    ) == [(3, 3), (6, 6)]
