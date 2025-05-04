def sanitize_unicode_nulls(data):
    """
    Recursively traverses dictionaries and lists to remove Unicode NULL
    characters (\u0000 or \x00) from strings.
    """
    if isinstance(data, dict):
        # Create a new dict to avoid modifying the original during iteration
        new_dict = {}
        for k, v in data.items():
            # Sanitize key if it's a string (less common but possible)
            sanitized_k = sanitize_unicode_nulls(k) if isinstance(k, str) else k
            new_dict[sanitized_k] = sanitize_unicode_nulls(v)
        return new_dict
    elif isinstance(data, list):
        # Create a new list
        return [sanitize_unicode_nulls(elem) for elem in data]
    elif isinstance(data, str):
        # Replace the problematic null byte U+0000 (\x00)
        # Replace with an empty string, which is usually safe for JSON.
        return data.replace('\u0000', '')
        # Alternative: Replace with a placeholder if you need to debug
        # return data.replace('\u0000', '[NULL_BYTE]')
    else:
        # Return integers, floats, booleans, None etc. as is
        return data