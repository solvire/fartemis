
class FundingStatus:
    """Constants for company funding statuses"""
    BOOTSTRAPPED = 'bootstrapped'
    SEED = 'seed'
    SERIES_A = 'a'
    SERIES_B = 'b'
    SERIES_C = 'c'
    SERIES_D = 'd'
    SERIES_E = 'e'
    SERIES_F = 'f'

    CHOICES = (
        (BOOTSTRAPPED, 'Bootstrapped'),
        (SEED, 'Seed'),
        (SERIES_A, 'Series A'),
        (SERIES_B, 'Series B'),
        (SERIES_C, 'Series C'),
        (SERIES_D, 'Series D'),
        (SERIES_E, 'Series E'),
        (SERIES_F, 'Series F'),
    )

class CompanyReviewSentiment:
    """Constants for company review sentiment"""
    POSITIVE = 'positive'
    NEUTRAL = 'neutral'
    NEGATIVE = 'negative'

    CHOICES = (
        (POSITIVE, 'Positive'),
        (NEUTRAL, 'Neutral'),
        (NEGATIVE, 'Negative'),
    )


COUNTRY_CODE_MAPPING = {
    "united states": "US", "usa": "US", "united states of america": "US",
    "canada": "CA", "mexico": "MX", "united kingdom": "GB", "uk": "GB", 
    "germany": "DE", "france": "FR", "italy": "IT", "spain": "ES",
    "china": "CN", "japan": "JP", "india": "IN", "australia": "AU",
    "brazil": "BR", "russia": "RU", "south africa": "ZA",
    # Add more as needed
}