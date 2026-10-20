#! /bin/bash

bin_path=$(dirname $(readlink -f $0))
HCopybin=${bin_path}/bin/wav2mfcc.py
svmscalebin=svm-scale
svmpredictbin=svm-predict

if [ $# -ne 2 ]; then
    echo "Usage: $ bash $0 (wav file) (outputfile)"
    exit 1;
fi


# SVM をテストし、推定された話者番号を出力する

wav=$1
HCopyConf=${bin_path}/config/config.HCopy
global_cmn=${bin_path}/bin/global_cmn.py
makeGMMbin=${bin_path}/bin/map_adapt.py
extractSVbin=${bin_path}/bin/extract_svs
extract_mu_sigma_w=${bin_path}/bin/extract_mu_sigma_w
SVbin2libsvm=${bin_path}/bin/svbin2libsvm.py
UBM=${bin_path}/UBM/jmodel

if [ ! -e ${bin_path}/tmp ];then
	mkdir -p ${bin_path}/tmp
fi

# wav --> MFCC
mkdir -p ${bin_path}/mfcc
segid=$(basename $wav .wav)
mfcctempfile=${bin_path}/mfcc/${segid}_tmp.mfcc
mfccfile=${bin_path}/mfcc/${segid}.mfcc
$HCopybin $wav $mfcctempfile
python3 $global_cmn $mfcctempfile $mfccfile
rm -f $mfcctempfile


# MAP 適応で GMM を推定し、SV を抽出
$makeGMMbin $mfccfile $UBM ${bin_path}/GMM/$(basename $mfccfile .mfcc) > /dev/null
echo $mfccfile | sed -e 's@\/mfcc\/@\/GMM\/@g' -e 's@\.mfcc@@g' > ${bin_path}/tmp/gmmlist.txt
$extractSVbin $UBM ${bin_path}/tmp/gmmlist.txt ${bin_path}/tmp/svs_bin
python $SVbin2libsvm 1 3200 ${bin_path}/tmp/svs_bin > ${bin_path}/tmp/test_tmp.dat
echo "1" > ${bin_path}/tmp/speaker.txt
paste -d ' ' ${bin_path}/tmp/speaker.txt ${bin_path}/tmp/test_tmp.dat > ${bin_path}/tmp/test.dat

rm -f ${bin_path}/tmp/speaker.txt ${bin_path}/tmp/gmmlist.txt ${bin_path}/tmp/svs_bin ${bin_path}/tmp/test_tmp.dat

# SVM をテスト
mkdir -p ${bin_path}/SVM
$svmscalebin -r ${bin_path}/SVM/scale.dat ${bin_path}/tmp/test.dat > ${bin_path}/tmp/s_test.dat
$svmpredictbin ${bin_path}/tmp/s_test.dat ${bin_path}/SVM/model ${bin_path}/tmp/result.dat > /dev/null

cp ${bin_path}/tmp/result.dat $2
rm -f ${bin_path}/tmp/test.dat ${bin_path}/tmp/s_test.dat ${bin_path}/tmp/result.dat 
