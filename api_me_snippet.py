# Add this route near the top of the route definitions in main.py
# (e.g. just before or after the /api/health or first @app.route)

@app.route('/api/me')
def api_me():
    """Return local auth session state for the frontend."""
    from flask import session as flask_session
    if flask_session.get('username'):
        return jsonify({
            'logged_in': True,
            'username': flask_session.get('username'),
            'is_admin': bool(flask_session.get('is_admin')),
        })
    return jsonify({'logged_in': False, 'username': None, 'is_admin': False})
