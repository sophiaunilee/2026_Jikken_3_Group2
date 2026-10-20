#!/usr/bin/env python3
import sys
import os
import struct
import numpy as np
from sklearn.mixture import GaussianMixture

def read_htk_user_file(filepath):
    """
    HTK形式のバイナリMFCCファイルを読み込み、TARGETKIND=MFCC_E_D_N (25次元) に変換します。
    NATURALREADORDER = TRUE (リトルエンディアン) に準拠します。
    """
    with open(filepath, 'rb') as f:
        # ヘッダーの読み込み (12バイト)
        header = f.read(12)
        if len(header) < 12:
            raise ValueError(f"Invalid HTK file header: {filepath}")
            
        n_samples, sample_period, sample_size, parm_kind = struct.unpack('<IIHH', header)
        
        # SOURCEKIND = MFCC_E_D の想定次元数 (12 + 1 + 12 + 1 = 26次元)
        # sampleSizeはバイト数なので、float(4バイト)で割る
        source_features = sample_size // 4
        
        if source_features != 26:
            print(f"Warning: Expected 26 dimensions for MFCC_E_D, but found {source_features}. Proceeding anyway.")
        
        # 残りの全フレームデータを読み込み
        data = f.read()
        expected_bytes = n_samples * sample_size
        if len(data) < expected_bytes:
            raise ValueError(f"File truncated. Expected {expected_bytes} bytes, got {len(data)} bytes.")
            
        # リトルエンディアンの float32 としてパース
        floats = struct.unpack(f'<{n_samples * source_features}f', data[:expected_bytes])
        X = np.array(floats, dtype=np.float32).reshape(n_samples, source_features)
        
        # --- MFCC_E_D (26次元) から MFCC_E_D_N (25次元) への変換 ---
        # HTKの配置: [MFCC_0..11 (12コ), E (1コ), dMFCC_0..11 (12コ), dE (1コ)]
        # インデックス12にある静的特徴の 'E' のみを削除し、最後の 'dE' は残します。
        if source_features == 26:
            # 0〜11列目(MFCC) と 13〜25列目(dMFCC + dE) を結合
            X_target = np.delete(X, 12, axis=1) # 12番目(13列目)の要素を削除
            return X_target
        else:
            # 次元数が異なる特殊な構成の場合は、末尾から2番目をEと仮定して落とすか、そのまま返します
            return X

def load_htk_gmm(filepath):
    """HTK形式のテキストファイルからGMMパラメータを読み込みます"""
    with open(filepath, 'r') as f:
        lines = f.readlines()

    weights, means, vars_list = [], [], []
    vec_size = None
    current_mean, current_var = None, None
    in_mean, in_var = False, False

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if "<VECSIZE>" in line:
            vec_size = int(line.split()[-1])
            continue
        if "<MIXTURE>" in line:
            weights.append(float(line.split()[-1]))
            continue
        if "<MEAN>" in line:
            in_mean = True
            current_mean = []
            continue
        if "<VARIANCE>" in line:
            in_var = True
            current_var = []
            continue
        if in_mean:
            current_mean.extend([float(x) for x in line.split()])
            if len(current_mean) >= vec_size:
                means.append(current_mean[:vec_size])
                in_mean = False
            continue
        if in_var:
            current_var.extend([float(x) for x in line.split()])
            if len(current_var) >= vec_size:
                vars_list.append(current_var[:vec_size])
                in_var = False
            continue

    if not weights and len(means) == 1:
        weights = [1.0]

    gmm = GaussianMixture(n_components=len(weights), covariance_type='diag')
    gmm.weights_ = np.array(weights, dtype=np.float64)
    gmm.means_ = np.array(means, dtype=np.float64)
    gmm.covariances_ = np.array(vars_list, dtype=np.float64)
    gmm.precisions_cholesky_ = 1.0 / np.sqrt(gmm.covariances_)
    return gmm

def herest_map_adaptation(ubm_gmm, X_mfcc, tau=10.0):
    """MAPTAUパラメータに基づく1回反復のMAP適応を行います"""
    n_samples, n_features = X_mfcc.shape
    n_components = ubm_gmm.n_components
    
    # E-Step: 負担率計算
    resp = ubm_gmm.predict_proba(X_mfcc)
    
    # 十分統計量の抽出
    n_k = resp.sum(axis=0)
    sum_x_k = np.dot(resp.T, X_mfcc)
    mu_k_hat = sum_x_k / (n_k[:, np.newaxis] + 1e-10)
    
    # M-Step: MAPTAUを用いた平均ベクトルの内挿更新
    alpha_k = n_k / (n_k + tau)
    alpha_k_reshaped = alpha_k[:, np.newaxis]
    adapted_means = alpha_k_reshaped * mu_k_hat + (1 - alpha_k_reshaped) * ubm_gmm.means_
    
    # 新しいGMMの構築 (共分散・重みはUBMを維持)
    adapted_gmm = GaussianMixture(n_components=n_components, covariance_type='diag')
    adapted_gmm.weights_ = np.copy(ubm_gmm.weights_)
    adapted_gmm.covariances_ = np.copy(ubm_gmm.covariances_)
    adapted_gmm.means_ = adapted_means
    adapted_gmm.precisions_cholesky_ = 1.0 / np.sqrt(adapted_gmm.covariances_)
    return adapted_gmm

def save_htk_gmm(gmm, filepath, model_name="adapted_model"):
    """GMMオブジェクトをHTKテキスト形式で書き出します"""
    n_components, n_features = gmm.means_.shape
    with open(filepath, 'w') as f:
        f.write('~o\n')
        f.write('<STREAMINFO> 1 {}\n'.format(n_features))
        f.write('<VECSIZE> {} <NULLD><MFCC_E_D_N>\n'.format(n_features))
        f.write('~h "{}"\n'.format(model_name))
        f.write('<BEGINHMM>\n')
        f.write('<NUMSTATES> 3\n')
        f.write('<STATE> 2\n')
        f.write('<NUMMIXES> {}\n'.format(n_components))
        for k in range(n_components):
            f.write('<MIXTURE> {} {:.6e}\n'.format(k + 1, gmm.weights_[k]))
            f.write('<MEAN> {}\n'.format(n_features))
            f.write(' {}\n'.format(" ".join(["{:.6e}".format(x) for x in gmm.means_[k]])))
            f.write('<VARIANCE> {}\n'.format(n_features))
            f.write(' {}\n'.format(" ".join(["{:.6e}".format(x) for x in gmm.covariances_[k]])))
            f.write('<GCONST> 1.0\n')
        f.write('<TRANSP> 3\n')
        f.write('    0.000000e+00 1.000000e+00 0.000000e+00\n')
        f.write('    0.000000e+00 0.000000e+00 1.000000e+00\n')
        f.write('    0.000000e+00 0.000000e+00 0.000000e+00\n')
        f.write('<ENDHMM>\n')

def main():
    if len(sys.argv) < 3:
        print("Usage: ./map_adapt.py <input_mfcc_file> <ubm_text_file> [output_text_file]")
        sys.exit(1)
        
    mfcc_path = sys.argv[1]
    ubm_path = sys.argv[2]
    
    if len(sys.argv) >= 4:
        output_path = sys.argv[3]
    else:
        output_path = os.path.splitext(os.path.basename(mfcc_path))[0] + "_adapted.gmm"
        
    print(f"Loading UBM: {ubm_path}")
    ubm = load_htk_gmm(ubm_path)
    
    # 読み込まれるUBMの次元数が25次元（MFCC_E_D_N）であることを確認
    if ubm.means_.shape[1] != 25:
        print(f"Warning: UBM feature dimension is {ubm.means_.shape[1]}, but target is 25.")
    
    print(f"Reading MFCC and converting to MFCC_E_D_N (25 dims): {mfcc_path}")
    X_mfcc = read_htk_user_file(mfcc_path)
    
    print(f"Input data shape after conversion: {X_mfcc.shape}")
    
    print(f"Running MAP Adaptation (MAPTAU=10)...")
    adapted_gmm = herest_map_adaptation(ubm, X_mfcc, tau=10.0)
    
    print(f"Saving adapted GMM to: {output_path}")
    model_name = os.path.splitext(os.path.basename(output_path))[0]
    save_htk_gmm(adapted_gmm, output_path, model_name=model_name)
    print("Done.")

if __name__ == "__main__":
    main()
