# Olive Ledger: English presentation script

The five sections below match the five slides. This is a rehearsal script, not text to read during the presentation. Target 1:45–1:55, including slide changes. The time depends on your speaking pace; a stopwatch rehearsal is required. The professor's fastest pace band requires finishing **under** two minutes.

## Slide 1 — 0:00–0:15

Olive Ledger helps students understand where their allowance goes and notice overspending early. It combines a white and olive interface with a Python backend, and also works through the command line.

## Slide 2 — 0:15–0:32

Users record income and expenses, choose payment methods, and set monthly or category budgets. The dashboard shows remaining money, spending patterns, and explained alerts. These screenshots use clearly labelled fictional demo data.

## Slide 3 — 0:32–0:54

Our architecture separates the interface, business rules, and storage. FastAPI and the argparse CLI call the same service functions, so validation and calculations behave consistently. This connects our project to functions, modules, dictionaries, and professional script structure from class.

## Slide 4 — 0:54–1:18

We convert validated decimal amounts into integer cents, so adding point one and point two gives exactly thirty cents. SQL parameters keep user input separate from queries. A transaction saves the record and its alerts together, and database constraints reject invalid relationships.

## Slide 5 — 1:18–1:50

An unusual expense must exceed twice its category average, using at least three previous expenses. The current expense never enters its own baseline. Budget alerts fire once at eighty and one hundred percent. Thirty automated tests cover invalid inputs, persistence, concurrency, and reports. The repository includes the CLI and setup instructions.


This deck uses one actual app screenshot so the timed talk does not depend on a live demo. Keep the app ready for questions afterward.

## Optional five-speaker allocation

One person per slide. Slide numbers correspond to topic sections, not assigned roles. Confirm the speakers yourselves; the script does not assign unverified contributions. Practise transitions without repeating greetings.

## Technical questions to practise

**Why integer cents instead of REAL?**

Binary floating-point cannot represent every decimal fraction exactly. We validate input using Decimal, then store integer cents. The database sums exact integers.

**What does `**args` do?**

It unpacks a dictionary into named function arguments. The parser's database path and command fields are removed before calling the service.

**Why share the service between the API and CLI?**

Both interfaces enforce identical rules without duplicating calculations. The service does not import FastAPI or browser code.

**How do you prevent SQL injection?**

Queries bind values through `?` or named placeholders. User text is data rather than part of the SQL statement.

**How is the anomaly calculated?**

We use at least three earlier-entered expenses in the same category dated on or before the target. The test `amount * count > total * 2` is equivalent to `amount > 2 * average` without floating-point rounding. Anomaly detection is a heuristic, not AI or machine learning.

**Why require three earlier expenses?**

It avoids making a comparison from a single sample. Three is a simple configurable design choice, not a statistically validated sample size.

**What happens if a save fails halfway through?**

Transaction insertion and alert insertion use the same SQLite transaction. The connection context commits them together or rolls both back on failure.

**What happens when an old transaction changes?**

Current totals recalculate. Its own anomaly alert is recalculated; other alerts remain event history. Historical budget alerts remain, and the UI says current budget values are on the Budgets page.

**Is the forecast guaranteed?**

No. It projects average recorded spending through today across the full month. A large early rent payment can exaggerate the estimate. The app labels it as an estimate and excludes future-dated expenses.

**Does the assistant use an AI model?**

No. It matches a limited set of question patterns and explains calculations from recorded data. Category suggestions use a dictionary of keywords and can be overridden.

**Does it work offline?**

The app's local UI, API, SQLite, built-in fonts and charts work without external CDNs after dependencies are installed. Interactive Swagger documentation uses its standard external assets, but the application UI does not.

**What are the limits?**

Single local user, one currency (TRY), no login or multi-user authorization, a rule-based spending heuristic, and a simple forecast. It is intended for a course project and personal local tracking.

**How does this connect to class?**

Functions separate tasks, dictionaries represent named data and keyword rules, conditionals determine thresholds, loops aggregate records and render categories, argparse defines CLI arguments, CSV handles file export, and a main guard keeps imports safe.

**Can you show the CLI?**

```powershell
.\.venv\Scripts\python.exe cli.py --db data/demo.db summary --month 2026-10
```