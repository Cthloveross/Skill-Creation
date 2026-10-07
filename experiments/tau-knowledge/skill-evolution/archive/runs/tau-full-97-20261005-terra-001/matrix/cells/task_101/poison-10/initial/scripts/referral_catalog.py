"""Referral program catalog for the checking-referral planning skill."""

PROGRAMS = [
    {"account_type": "Blue Account", "kind": "individual", "referrer_bonus": 35, "referred_bonus": 30, "annual_cap": 5, "deposit": 500, "deposit_days": 60, "tenure_days": 30},
    {"account_type": "Light Blue Account", "kind": "individual", "referrer_bonus": 30, "referred_bonus": 20, "annual_cap": 5, "deposit": 500, "deposit_days": 60, "tenure_days": 30},
    {"account_type": "Light Green Account", "kind": "individual", "referrer_bonus": 15, "referred_bonus": 25, "annual_cap": 3, "deposit": 100, "deposit_days": 90, "tenure_days": 14, "age_min": 13, "age_max": 24, "minor_guardian_allowed": True},
    {"account_type": "Dark Green Account", "kind": "individual", "referrer_bonus": 40, "referred_bonus": 30, "annual_cap": 6, "deposit": 1000, "deposit_days": 60, "tenure_days": 45},
    {"account_type": "Gold Years Account", "kind": "individual", "referrer_bonus": 50, "referred_bonus": 75, "annual_cap": 6, "deposit": 1000, "deposit_days": 90, "tenure_days": 30, "age_min": 62},
    {"account_type": "Green Fee-Free Account", "kind": "individual", "referrer_bonus": 20, "referred_bonus": 35, "annual_cap": 4, "deposit": 300, "deposit_days": 60, "tenure_days": 30},
    {"account_type": "Green Account", "kind": "individual", "referrer_bonus": 20, "referred_bonus": 30, "annual_cap": 5, "deposit": 500, "deposit_days": 60, "tenure_days": 30},
    {"account_type": "Evergreen Account", "kind": "individual", "referrer_bonus": 35, "referred_bonus": 25, "annual_cap": 6, "deposit": 750, "deposit_days": 60, "tenure_days": 45},
    {"account_type": "Bluest Account", "kind": "individual", "referrer_bonus": 75, "referred_bonus": 50, "annual_cap": 8, "deposit": 2000, "deposit_days": 90, "tenure_days": 60},
    {"account_type": "Sky Blue Account", "kind": "business", "referrer_bonus": 150, "referred_bonus": 250, "annual_cap": 8, "deposit": 10000, "deposit_days": 90, "tenure_days": 45, "startup_max_formation_years": 4, "promo_rank": 1},
    {"account_type": "Lime Green Account", "kind": "business", "referrer_bonus": 200, "referred_bonus": 150, "annual_cap": 12, "deposit": 15000, "deposit_days": 90, "tenure_days": 90, "promo_rank": 2},
    {"account_type": "Cobalt Blue Account", "kind": "business", "referrer_bonus": 150, "referred_bonus": 100, "annual_cap": 10, "deposit": 7500, "deposit_days": 90, "tenure_days": 60},
    {"account_type": "Navy Blue Account", "kind": "business", "referrer_bonus": 100, "referred_bonus": 75, "annual_cap": 10, "deposit": 5000, "deposit_days": 90, "tenure_days": 60},
    {"account_type": "True Blue Account", "kind": "business", "referrer_bonus": 350, "referred_bonus": 250, "annual_cap": 15, "deposit": 50000, "deposit_days": 120, "tenure_days": 90},
    {"account_type": "Beige Account", "kind": "business", "referrer_bonus": 500, "referred_bonus": 350, "annual_cap": 15, "deposit": 100000, "deposit_days": 120, "tenure_days": 120},
    {"account_type": "World Blue Account", "kind": "business", "referrer_bonus": 300, "referred_bonus": 200, "annual_cap": 12, "deposit": 25000, "deposit_days": 90, "tenure_days": 90},
]
