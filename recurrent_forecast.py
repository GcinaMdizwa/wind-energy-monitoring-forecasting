"""Direct multi-horizon RNN/LSTM experiment with chronological validation.

No shuffled time split, future feature leakage or full-series scaler fitting.
Archive weather target is wind speed, never falsely labelled measured power.
"""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from wind_data import power_curve

FEATURES = ['wind_speed', 'direction_sin', 'direction_cos', 'hour_sin', 'hour_cos', 'year_sin', 'year_cos']


class HybridRNNLSTM(nn.Module):
    def __init__(self, horizon=24, architecture='hybrid', hidden=32):
        super().__init__()
        if architecture not in ('hybrid', 'lstm', 'rnn'):
            raise ValueError('Unknown architecture')
        self.architecture = architecture
        if architecture in ('hybrid', 'rnn'):
            self.rnn = nn.RNN(7, hidden, batch_first=True, nonlinearity='tanh')
        if architecture in ('hybrid', 'lstm'):
            self.lstm = nn.LSTM(7, hidden, batch_first=True)
        self.head = nn.Sequential(nn.Linear(hidden * (2 if architecture == 'hybrid' else 1), 32),
                                  nn.ReLU(), nn.Linear(32, horizon))

    def forward(self, x):
        embeddings = []
        if self.architecture in ('hybrid', 'rnn'):
            embeddings.append(self.rnn(x)[0][:, -1])
        if self.architecture in ('hybrid', 'lstm'):
            embeddings.append(self.lstm(x)[0][:, -1])
        return self.head(torch.cat(embeddings, dim=1))


def feature_array(frame):
    t = pd.to_datetime(frame['timestamp'], utc=True)
    d = np.deg2rad(frame['wind_direction_deg'].to_numpy(dtype=float))
    h = t.dt.hour.to_numpy() * 2 * np.pi / 24
    y = (t.dt.dayofyear.to_numpy() - 1) * 2 * np.pi / 365.25
    return np.column_stack([frame['wind_speed_mps'], np.sin(d), np.cos(d),
                            np.sin(h), np.cos(h), np.sin(y), np.cos(y)]).astype('float32')


def prepare(frame, lookback=48, horizon=24):
    frame = frame.sort_values('timestamp').reset_index(drop=True).copy()
    t = pd.to_datetime(frame['timestamp'], utc=True)
    if len(frame) < 1000 or t.duplicated().any() or not (t.diff().dropna() == pd.Timedelta(hours=1)).all():
        raise ValueError('Training needs at least 1000 complete, unique hourly observations.')
    a = feature_array(frame)
    if not np.isfinite(a).all() or (a[:, 0] < 0).any() or not frame['wind_direction_deg'].between(0, 360).all():
        raise ValueError('Invalid wind observations; resolve missing or out-of-range values.')
    n = len(a)
    train_end, val_end = int(n * .7), int(n * .85)
    mean, scale = a[:train_end].mean(0), a[:train_end].std(0)
    scale = np.maximum(scale, 1e-5)
    z = (a - mean) / scale
    # Every target in each split lies inside its own chronological interval.
    def windows(start, stop):
        origins = np.arange(max(lookback, start), stop - horizon + 1)
        x = np.stack([z[o-lookback:o] for o in origins])
        y = np.stack([z[o:o+horizon, 0] for o in origins])
        return x, y, origins
    return frame, mean, scale, (windows(lookback, train_end), windows(train_end, val_end), windows(val_end, n))


def train(frame, directory, metadata, architecture='hybrid', epochs=12, callback=lambda **kw: None):
    torch.manual_seed(42)
    torch.set_num_threads(2)
    lookback, horizon = 48, 24
    frame, mean, scale, splits = prepare(frame, lookback, horizon)
    model = HybridRNNLSTM(horizon, architecture)
    optimizer = torch.optim.Adam(model.parameters(), lr=.001)
    criterion = nn.MSELoss()
    x, y, _ = splits[0]
    loader = DataLoader(TensorDataset(torch.from_numpy(x), torch.from_numpy(y)), batch_size=256, shuffle=True,
                        generator=torch.Generator().manual_seed(42))
    vx, vy, _ = splits[1]
    best, best_state, wait, curve = float('inf'), None, 0, []
    for epoch in range(epochs):
        model.train()
        total = 0
        for bx, by in loader:
            optimizer.zero_grad()
            loss = criterion(model(bx), by)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1)
            optimizer.step()
            total += loss.item() * len(bx)
        model.eval()
        with torch.no_grad():
            val = sum(criterion(model(torch.from_numpy(vx[i:i+256])), torch.from_numpy(vy[i:i+256])).item() * len(vx[i:i+256])
                      for i in range(0, len(vx), 256)) / len(vx)
        curve.append({'epoch': epoch+1, 'train_mse_scaled': total/len(x), 'validation_mse_scaled': val})
        callback(stage='Training', epoch=epoch+1, epochs=epochs, loss=round(val, 5))
        if val < best:
            best, best_state, wait = val, deepcopy(model.state_dict()), 0
        else:
            wait += 1
        if wait >= 4:
            break
    model.load_state_dict(best_state)
    model.eval()
    tx, ty, origins = splits[2]
    with torch.no_grad():
        prediction = np.concatenate([model(torch.from_numpy(tx[i:i+256])).numpy() for i in range(0, len(tx), 256)])
    prediction = np.maximum(prediction * scale[0] + mean[0], 0)
    actual = ty * scale[0] + mean[0]
    baseline = np.repeat(frame['wind_speed_mps'].to_numpy()[origins-1, None], horizon, axis=1)
    def score(p):
        return {'mae_mps': float(np.mean(np.abs(p-actual))), 'rmse_mps': float(np.sqrt(np.mean((p-actual)**2)))}
    report = {**metadata, 'architecture': architecture, 'lookback_hours': lookback, 'horizon_hours': horizon,
              'features': FEATURES, 'trained_at': datetime.now(timezone.utc).isoformat(),
              'split': '70% training / 15% validation / 15% test; non-overlapping target periods',
              'train_last_target': str(frame.iloc[int(len(frame)*.7)-1]['timestamp']),
              'test_first_target': str(frame.iloc[origins[0]]['timestamp']),
              'training_windows': len(x), 'test_windows': len(tx), 'epochs_run': len(curve),
              'model': score(prediction), 'persistence': score(baseline), 'learning_curve': curve,
              'by_horizon': [{'hour': j+1, 'mae_mps': float(np.mean(abs(prediction[:,j]-actual[:,j]))),
                              'persistence_mae_mps': float(np.mean(abs(baseline[:,j]-actual[:,j])))} for j in range(horizon)],
              'test_preview': [{'time': str(frame.iloc[o]['timestamp']), 'actual': float(actual[i,0]),
                                'prediction': float(prediction[i,0]), 'persistence': float(baseline[i,0])}
                               for i,o in list(enumerate(origins))[-168:]],
              'limitations': 'Single-site reanalysis experiment, overlapping rolling test windows, not independent forecast runs or turbine telemetry. No calibrated uncertainty or automatic online adaptation.'}
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    torch.save({'state': model.state_dict(), 'mean': mean.tolist(), 'scale': scale.tolist(),
                'architecture': architecture, 'horizon': horizon}, directory/'model.pt')
    (directory/'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    frame.tail(lookback).to_csv(directory/'last_window.csv', index=False)
    return report


def predict(directory, recent, rated_kw=2000):
    directory = Path(directory)
    checkpoint = torch.load(directory/'model.pt', map_location='cpu', weights_only=True)
    report = json.loads((directory/'report.json').read_text(encoding='utf8'))
    # Inference uses training statistics, never fits a scaler to the new window.
    a = feature_array(recent.tail(48))
    if len(a) != 48 or not np.isfinite(a).all():
        raise ValueError('48 complete recent hourly observations are required.')
    mean, scale = np.array(checkpoint['mean']), np.array(checkpoint['scale'])
    model = HybridRNNLSTM(checkpoint['horizon'], checkpoint['architecture'])
    model.load_state_dict(checkpoint['state'])
    model.eval()
    with torch.no_grad():
        v = model(torch.tensor(((a-mean)/scale)[None], dtype=torch.float32)).numpy()[0]
    v = np.maximum(v*scale[0]+mean[0], 0)
    issued = pd.to_datetime(recent.iloc[-1]['timestamp'], utc=True)
    return {'issued_at': str(issued), 'trained_at': report['trained_at'],
            'architecture': checkpoint['architecture'], 'input_source': 'Latest 48 modelled weather hours; not sensor observations',
            'rows': [{'time': (issued+pd.Timedelta(hours=i+1)).isoformat(), 'speed': float(s),
                      'power_kw': float(power_curve(s, rated_kw))} for i,s in enumerate(v)]}
