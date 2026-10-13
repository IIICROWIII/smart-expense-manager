"""SQL access. All caller-provided values use bound parameters."""

TRANSACTION_SELECT = """SELECT t.*, c.name AS category FROM transactions t
    JOIN categories c ON c.id=t.category_id"""


def transaction(conn, identifier):
    row = conn.execute(TRANSACTION_SELECT + " WHERE t.id=?", (identifier,)).fetchone()
    return dict(row) if row else None


def transactions(conn, month=None, kind=None, category_id=None, search=None, unusual=False, limit=15, offset=0):
    clauses, values = [], []
    if month:
        clauses.append("substr(t.date,1,7)=?")
        values.append(month)
    if kind:
        clauses.append("t.kind=?")
        values.append(kind)
    if category_id is not None:
        clauses.append("t.category_id=?")
        values.append(category_id)
    if search:
        clauses.append("(instr(lower(t.description),lower(?))>0 OR instr(lower(c.name),lower(?))>0)")
        values.extend([search, search])
    if unusual:
        clauses.append("EXISTS(SELECT 1 FROM alerts a WHERE a.transaction_id=t.id AND a.kind='unusual')")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    total = conn.execute("SELECT COUNT(*) FROM transactions t JOIN categories c ON c.id=t.category_id" + where, values).fetchone()[0]
    rows = conn.execute(TRANSACTION_SELECT + where + " ORDER BY t.date DESC,t.id DESC LIMIT ? OFFSET ?", values + [limit, offset]).fetchall()
    return {"items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}
