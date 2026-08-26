"""Business services. content_generator.py is the pluggable AI-content
seam (see its own docstring); route handlers otherwise talk to the
database directly via src/repositories - CLAUDE.md explicitly discourages
unnecessary abstraction, so a repository-per-resource layer isn't added
just for its own sake.
"""
