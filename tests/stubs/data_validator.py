"""TEST STAND-IN for the project's real data_validator.py (not shipped to the user)."""


def validate_dataset(df):
    return [
        {"check": "Not empty", "status": "Pass" if len(df) else "Fail"},
        {"check": "No duplicate rows", "status": "Pass" if not df.astype(str).duplicated().any() else "Warning"},
    ]
