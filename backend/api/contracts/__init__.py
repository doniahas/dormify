"""
HTTP contract layer of the Dormify API.

The modules here sit at the view/serializer boundary, never below it:

- ``errors``   - the error-body builders every hand-written view uses, so
                 the live error shapes ({'error'}, {'error','errorEn'},
                 {'success': False, 'error', ...}) are constructed in one
                 place and characterized once.
- ``requests`` - typed parsers for the request bodies that the thin views
                 read by hand rather than through a DRF serializer. Each
                 parser reproduces the endpoint's historical acceptance
                 rules exactly (what is accepted, what defaults apply, what
                 message a rejection carries) and raises ValueError with
                 the user-facing message; the view maps it to its status.

Domain modules (api.domains.*) never import from this package.
"""
