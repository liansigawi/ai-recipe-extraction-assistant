"""Reading pasted recipe text with Claude.

    output.py   the shape Claude's answer must have (a JSON schema the API enforces)
    prompt.py   the instructions, and how the pasted text is wrapped as data
    claude.py   the call to the Claude API, and its failures as clear errors
    review.py   checks every part of the answer and turns it into a draft with review issues

Only review.py's result is ever saved, and only as a draft: the person reviews it and
saves it explicitly.
"""
