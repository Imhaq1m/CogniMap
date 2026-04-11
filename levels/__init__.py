"""
CogniMap Levels Module — All Bloom's Taxonomy level blueprints.

Usage:
    from levels import register_all_levels
    register_all_levels(app)
"""

from levels.level1_remember.routes import level1_bp
from levels.level2_understand.routes import level2_bp
from levels.level3_apply.routes import level3_bp
from levels.level4_analyze.routes import level4_bp
from levels.level5_evaluate.routes import level5_bp
from levels.level6_create.routes import level6_bp


def register_all_levels(app):
    """Register all level blueprints with the Flask app."""
    app.register_blueprint(level1_bp)
    app.register_blueprint(level2_bp)
    app.register_blueprint(level3_bp)
    app.register_blueprint(level4_bp)
    app.register_blueprint(level5_bp)
    app.register_blueprint(level6_bp)
