#!/usr/bin/env python3
import sys
import os
import struct
import numpy as np
import librosa
import scipy.fftpack
import scipy.signal

def extract_htk_mfcc_e_d(wav_path):
    """WAVファイルからHTK互換のMFCC_E_D特徴量を抽出する"""
    # 1. 音声ファイルの読み込み（SOURCERATE=625 は 16000Hz）
    y, sr = librosa.load(wav_path, sr=16000)
    
    # 2. 直流成分（平均値）の除去 (ZMEANSOURCE = T)
    y = y - np.mean(y)
    
    # 3. プリエンファシス（PREEMCOEF = 0.97）
    y_preemph = librosa.effects.preemphasis(y, coef=0.97)
    
    # 4. パラメータ設定 (WINDOWSIZE=25ms, TARGETRATE=10ms)
    n_fft = int(0.025 * sr)       # 400 サンプル
    hop_length = int(0.010 * sr)  # 160 サンプル
    
    # 5. STFTの計算 (USEHAMMING = T, center=False)
    stft = librosa.stft(y_preemph, n_fft=n_fft, hop_length=hop_length, 
                        window='hamming', center=False)
    amplitude_spec = np.abs(stft)
    
    # 6. 对数エネルギー（Log Energy）の計算 (RAWENERGY = F の挙動)
    n_frames = stft.shape[1]
    energy = np.zeros(n_frames)
    window = scipy.signal.windows.hamming(n_fft, sym=False)
    
    for t in range(n_frames):
        start = t * hop_length
        end = start + n_fft
        if end <= len(y_preemph):
            frame_signal = y_preemph[start:end] * window
            energy[t] = np.log(np.maximum(np.sum(frame_signal ** 2), 1e-10))
            
    # 7. メルフィルタバンクの作成 (NUMCHANS = 24)
    mel_basis = librosa.filters.mel(sr=sr, n_fft=n_fft, n_mels=24, 
                                    fmin=0, fmax=sr/2, htk=True, norm=None)
    mel_spec = np.dot(mel_basis, amplitude_spec)
    log_mel_spec = np.log(np.maximum(mel_spec, 1e-10))
    
    # 8. 離散コサイン変換 (NUMCEPS = 12)
    mfcc_full = scipy.fftpack.dct(log_mel_spec, type=3, axis=0, norm='ortho')
    mfcc = mfcc_full[1:13, :]  # 1〜12次を抽出
    
    # 9. 特徴量の結合 [MFCC (12次元) + Energy (1次元)]
    mfcc_e = np.vstack([mfcc, energy])
    
    # 10. デルタ特徴量の計算（左右2フレーム、計5フレーム窓）
    delta = librosa.feature.delta(mfcc_e, width=5, order=1, mode='interp')
    
    # 11. 最終的な特徴量の結合 [MFCC_E + Delta] (計26次元)
    mfcc_e_d = np.vstack([mfcc_e, delta])
    
    # (フレーム数, 特徴量次元数) に転置
    return mfcc_e_d.T

def save_htk_file_little_endian(filename, features, sample_period=100000):
    """NATURALREADORDER = TRUE 用にリトルエンディアンでHTKファイルを保存する"""
    n_samples, vec_size = features.shape
    sample_byte_size = vec_size * 4
    htk_parm_kind = 326  # MFCC_E_D
    
    features_ndarray = np.array(features, dtype='<f4')
    
    with open(filename, 'wb') as f:
        header = struct.pack('<IIHH', n_samples, sample_period, sample_byte_size, htk_parm_kind)
        f.write(header)
        f.write(features_ndarray.tobytes())

if __name__ == "__main__":
    # 引数のチェック（スクリプト名を含めて3つ必要）
    if len(sys.argv) != 3:
        print("Usage: python3 wav2mfcc.py <input_wav> <output_mfc>")
        sys.exit(1)
        
    input_wav = sys.argv[1]   # 第一引数
    output_mfc = sys.argv[2]  # 第二引数
    
    if not os.path.exists(input_wav):
        print(f"Error: Input file '{input_wav}' does not exist.")
        sys.exit(1)
        
    try:
        # 特徴量抽出と保存の実行
        features = extract_htk_mfcc_e_d(input_wav)
        save_htk_file_little_endian(output_mfc, features)
        print(f"Success: {input_wav} -> {output_mfc} ({features.shape[0]} frames)")
    except Exception as e:
        print(f"Error occurred during processing: {e}")
        sys.exit(1)
