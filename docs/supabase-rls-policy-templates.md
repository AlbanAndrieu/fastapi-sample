## Supabase RLS Policy Templates

**note table**

```sql
ALTER TABLE note ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated users can view their notes"
ON note FOR SELECT TO authenticated
USING ((select auth.uid()) = user_id);

CREATE POLICY "Authenticated users can insert their notes"
ON note FOR INSERT TO authenticated
WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "Authenticated users can update their notes"
ON note FOR UPDATE TO authenticated
USING ((select auth.uid()) = user_id)
WITH CHECK ((select auth.uid()) = user_id);

CREATE POLICY "Authenticated users can delete their notes"
ON note FOR DELETE TO authenticated
USING ((select auth.uid()) = user_id);
```

**user table**

```sql
ALTER TABLE "user" ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated can select users"
ON "user" FOR SELECT TO authenticated
USING (true);
```

**sensor_reading table**

```sql
ALTER TABLE sensor_reading ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Authenticated can select sensor readings"
ON sensor_reading FOR SELECT TO authenticated
USING (true);
```

**Best practices:**
- Restrict note/user access to only owner if needed.
- Make use of `WITH CHECK` for inserts/updates.
- For more granular control or admin privileges, specify the `role` or add additional policy clauses.
- Always test policies after application—API endpoints will be blocked until a SELECT policy exists.

---

Copy-paste these templates into your Supabase SQL editor and adjust according to your schema (column names).

(End of templates)
