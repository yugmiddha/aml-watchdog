import os
import uuid
import random
import datetime
import numpy as np
import pandas as pd
from typing import List, Dict, Any

LOCATIONS = ['US', 'UK', 'UAE', 'Germany', 'Panama', 'Cyprus', 'Singapore', 'Cayman Islands', 'Canada', 'Switzerland', 'France']
PAYMENT_TYPES = ['Credit Card', 'Wire Transfer', 'ACH', 'Cash Deposit', 'Cheque', 'Cross-border']
CURRENCIES = ['USD', 'EUR', 'GBP', 'AED', 'CHF']

LAUNDERING_PATTERNS = [
    'Smurfing', 'Structuring', 'Cycle', 'Fan_In', 'Fan_Out', 
    'Deposit-Send', 'Layered_Fan_In', 'Layered_Fan_Out', 'Scatter-Gather'
]

def generate_scaled_transactions(total_records: int = 100000, laundering_ratio: float = 0.02, output_file: str = None) -> pd.DataFrame:
    print(f'[*] Generating {total_records:,} scalable transactions with NumPy and Pandas (laundering_ratio={laundering_ratio:.1%})...')
    
    num_laundering = int(total_records * laundering_ratio)
    num_normal = total_records - num_laundering
    
    # Generate Normal Transactions using NumPy
    normal_amounts = np.clip(np.random.lognormal(mean=5.8, sigma=1.1, size=num_normal), 15.0, 45000.0).round(2)
    sender_accs = np.random.randint(1000000000, 9999999999, size=total_records)
    receiver_accs = np.random.randint(1000000000, 9999999999, size=total_records)
    
    # Laundering Amounts & Typologies
    laundering_amounts = np.random.choice([
        np.random.uniform(8800.0, 9950.0, size=num_laundering // 2),  # Structuring
        np.random.uniform(25000.0, 125000.0, size=num_laundering - (num_laundering // 2))  # High-volume layering
    ]).flatten().round(2)
    
    all_amounts = np.concatenate([normal_amounts, laundering_amounts])
    is_laundering_flags = np.array([0] * num_normal + [1] * num_laundering)
    
    laundering_types = ['Normal'] * num_normal + [random.choice(LAUNDERING_PATTERNS) for _ in range(num_laundering)]
    
    # Shuffle together
    indices = np.arange(total_records)
    np.random.shuffle(indices)
    
    now = datetime.datetime.now()
    dates = [(now - datetime.timedelta(minutes=int(i))).strftime('%Y-%m-%d') for i in range(total_records)]
    times = [(now - datetime.timedelta(seconds=int(i * 15))).strftime('%H:%M:%S') for i in range(total_records)]
    
    df = pd.DataFrame({
        'tx_id': [f'TX-{uuid.uuid4().hex[:10].upper()}' for _ in range(total_records)],
        'date': dates,
        'time': times,
        'timestamp': [f'{d}T{t}' for d, t in zip(dates, times)],
        'sender_account': sender_accs[indices].astype(str),
        'receiver_account': receiver_accs[indices].astype(str),
        'amount': all_amounts[indices],
        'payment_currency': np.random.choice(CURRENCIES, size=total_records),
        'received_currency': np.random.choice(CURRENCIES, size=total_records),
        'sender_bank_location': np.random.choice(LOCATIONS, size=total_records),
        'receiver_bank_location': np.random.choice(LOCATIONS, size=total_records),
        'payment_type': np.random.choice(PAYMENT_TYPES, size=total_records),
        'is_laundering': is_laundering_flags[indices],
        'laundering_type': [laundering_types[i] for i in indices]
    })
    
    if output_file:
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        df.to_parquet(output_file, index=False)
        print(f'[+] Scaled transaction dataset saved to {output_file}')
        
    return df

def generate_live_stream_batch(batch_size: int = 15) -> List[Dict[str, Any]]:
    df = generate_scaled_transactions(total_records=batch_size, laundering_ratio=0.30)
    return df.to_dict(orient='records')
