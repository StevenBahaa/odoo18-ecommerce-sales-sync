import re

def normalize_phone_digits(phone_str):
    """
    Normalizes a phone number by stripping all non-digit characters.
    Does not infer or modify country codes.
    Example:
        '+966 50 000 0001' -> '966500000001'
        '+966-50-000-0001' -> '966500000001'
    """
    if not phone_str:
        return False
    # Remove all non-digit characters
    digits = re.sub(r'\D', '', str(phone_str))
    return digits if digits else False
