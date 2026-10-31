# dryer

dryer finds candidate duplicate code in Clojure, Java, Go, TypeScript, Rust, Python, and Ruby (experimental). One run detects the language of each source file, normalizes that language's forms, and reports pairs whose structure is close enough to review.

Clojure follows [dry4clj](https://github.com/unclebob/dry4clj). The other languages use the same idea on the functions and methods [crapper](https://github.com/unclebob/crapper) and [mutator](https://github.com/unclebob/mutator) already treat as one unit. A form is only compared with forms written in the same language.

The score is Jaccard similarity of structural fingerprints:

```text
score = shared fingerprints / all fingerprints seen in either form
```

A score of `1.0` means the normalized structures have the same fingerprint set. The default `--threshold 0.82` reports candidates close enough to be worth review.

These two functions score `1.0`. The names, locals, predicates, and mapped functions differ, and those incidental symbols normalize away. A default run still skips them: they are three lines, and the default minimum is four.

```clojure
(defn alpha [xs]
  (let [ys (filter odd? xs)]
    (map inc ys)))

(defn beta [items]
  (let [kept (filter even? items)]
    (map dec kept)))
```

The same shape in the other languages scores `1.0` too: the called function or method stays, and the locals do not.

```java
int alpha(int[] xs) {
  int[] ys = filter(xs, odd);
  return map(ys, inc);
}
```

```python
def beta(items):
    kept = filter(items, even)
    return map(kept, dec)
```

What stays is the call or method name, the operator, and the shape of the tree. What drops out is the local name, the field name, the literal, and the keyword. A Clojure keyword call `(:kind m)` and `(:id row)` is the same shape. So is `order.total` and `row.amount`.

Ruby support is experimental and was added with the help of Claude Opus 5.5. Its rules may still change as it is tried on more Ruby code.

Ruby has no fields: `order.total` sends the message `total`, so in Ruby `order.total` and `row.amount` differ, and so do `map(&:total)` and `map(&:amount)`. A class that receives a message stays as well: `Invoice.new` is not `Receipt.new`, while `raise ArgumentError` and `raise TypeError` are the same shape. Symbols are literals, so `row[:id]` and `row["id"]` match. A block is part of its call and is compared with it.

## Run

```bash
./dryer
```

The first run creates `.venv` and installs the tool. From a project root it walks the tree, skips `test`, `spec`, `vendor`, `node_modules`, and `target`, and writes two results:

- a report on stdout, closest match first
- `.metrics/dry.edn`, replaced on every successful analysis

```bash
./dryer src/demo src/ui          # these files and trees
./dryer --changed                # git additions and edits
./dryer billing                  # path fragment
./dryer --threshold 0.9 src
./dryer --edn --min-lines 3 src
```

```text
--threshold N    Minimum structural similarity score, default 0.82
--min-lines N    Minimum source lines in a candidate form, default 4
--min-nodes N    Minimum normalized syntax nodes, default 20
--format F       text or edn, default text
--edn            Same as --format edn
--text           Same as --format text
--include-migrations
                 Compare Rails migrations and db/schema.rb too
```

Rails migrations repeat by design and are not edited once they run, so a walk leaves out `db/migrate` and `db/schema.rb` and says so on stderr:

```text
dryer: skipped 37 migration files (db/migrate, db/schema.rb); pass --include-migrations to compare them
```

Naming the directory, as in `./dryer db/migrate`, compares them without the flag.

Normalized syntax nodes are the structural pieces left after incidental names and literals are replaced. `--min-nodes` drops forms smaller than that before comparison.

Default text output for the invoice and receipt from dry4clj. They differ by one extra binding:

```text
DUPLICATE score=0.89
  src/billing/invoice.clj:3-13
  src/billing/receipt.clj:3-14
```

`.metrics/dry.edn` is the same report dry4clj prints as EDN, with the language added:

```clojure
{:candidates
 [{:score 0.890909090909
   :language "clojure"
   :left {:file "src/billing/invoice.clj", :start-line 3, :end-line 13}
   :right {:file "src/billing/receipt.clj", :start-line 3, :end-line 14}
   :left-nodes 158
   :right-nodes 166}]}
```

## What each language compares

| Language | Candidate | Left out |
| --- | --- | --- |
| Clojure | every top-level form except `ns` | reader-conditional branches other than `:clj` |
| Java | methods with a body | constructors, abstract methods, methods inside anonymous or local classes |
| Go | functions and methods with a body | function literals stay inside the enclosing function |
| TypeScript | functions, methods, and top-level arrow functions | callbacks nested inside another function |
| Rust | functions and methods with a body | functions inside `mod tests`, and closures |
| Python | functions and methods | functions nested inside another function |
| Ruby (experimental) | `def` and `def self.` methods, including those in `class << self`, `private def`, and blocks such as `class_methods do` | methods that only store their arguments (`@name = name`, literals, `super`), methods defined inside another method, blocks and lambdas outside a method, `*_spec.rb`, `*_test.rb`, `test_*.rb`, the spec/rails/test helpers, and migrations |

Clojure reader conditionals keep the `:clj` branch, as dry4clj does. Syntax-quote is kept as a `syntax-quote` form rather than expanded.

A missing or unreadable Clojure form is reported on stderr. Forms read before it are still compared. The run exits `0` after a report, `1` on a usage error, and `2` on an unknown `--format`.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```
