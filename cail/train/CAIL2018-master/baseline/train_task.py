#encoding: utf8

'''
支持py3语法
'''
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import absolute_import
from __future__ import division
from pprint import pprint
#import six 
from time import time
from datetime import datetime

import fcntl 

from sklearn.feature_extraction.text import TfidfVectorizer 
from sklearn.linear_model import SGDClassifier
from sklearn.model_selection import GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.cross_validation import PredefinedSplit

import json
from predictor import data
import sys
from judger import Judger

from sklearn.svm import LinearSVC
from sklearn.externals import joblib
from sklearn.ensemble import AdaBoostClassifier
from sklearn.linear_model import LogisticRegression
import numpy as np
import pickle
import pdb



'''
    logfilename="../log/train.log
    logger = create_logger(logfilename)

    logger = logging.getLogger()
    infostr = "tagid: %s or method:%s is not digit." % (tagid, method)
    logger.info(infostr)
    logger.debug(infostr)
'''
def create_logger(logfilename=None, logName=None) :
    import logging,logging.handlers
    logger = logging.getLogger(logName)
    infohdlr = None
    if logfilename ==None:
        infohdlr = logging.StreamHandler(sys.stdout)
    else:
        infohdlr = logging.FileHandler(logfilename)
    infohdlr.setLevel(logging.INFO)
    #detail

    formatter = logging.Formatter('%(asctime)s %(levelname)6s  %(threadName)-12s %(filename)-10s  %(lineno)4d:%(funcName)16s|| %(message)s')
    formatter = logging.Formatter('%(asctime)s %(levelname)6s %(message)s')

    infohdlr.setFormatter(formatter)

    logger.addHandler(infohdlr)

    logger.setLevel(logging.DEBUG)
    return logger


def line2sample(line):
    ans = {}
    arr = line.strip().split('\t')
    if len(arr) != 5:
        return None

    ans['accusation'] = [int(x) for x in arr[1].split(',')]
    ans['articles'] = [int(x) for x in arr[2].split(',')]
    ans['imprisonment'] = int(arr[3])

    ws = arr[4].split(',')
    #words = [x.split(' ')[0] for x in ws ]
    word_poses = [x.split(' ') for x in ws ]
    words = [x for x,p in word_poses if p[0] != u'u' and p[0] != u'x']
    text = ' '.join(words)

    return (ans, text)

class PredictorLocal(object):
    def __init__(self, tfidf_model, accu_model, law_model, time_model):
        self.tfidf = tfidf_model
        self.accu = accu_model
        self.law = law_model
        self.time = time_model

    def predict_law(self, vec):
        y = [-1]
        if self.law != None:
            y = self.law.predict(vec)
        return [y[0]]
    
    def predict_accu(self, vec):
        y = [-1]
        if self.accu != None:
            y = self.accu.predict(vec)
        return [y[0]]
    
    def predict_time(self, vec):
        if self.time == None:
            return -2

        y = self.time.predict(vec)[0]
        
        #返回每一个罪名区间的中位数
        if y == 0:
            return -2
        if y == 1:
            return -1
        if y == 2:
            return 120
        if y == 3:
            return 102
        if y == 4:
            return 72
        if y == 5:
            return 48
        if y == 6:
            return 30
        if y == 7:
            return 18
        else:
            return 6
        
    def predict_file(self, test_filename):
        all_test_predicts = []
        all_test_labels = []
        test_f = open(test_filename, 'rb')
        for line in test_f:
            line = line.decode('utf8')
            sample = line2sample(line)
            if None == sample:
                continue

            label, text = sample
            vec = self.tfidf.transform([text])
            ans = {}
            ans['accusation'] = self.predict_accu(vec)
            ans['articles'] = self.predict_law(vec)
            ans['imprisonment'] = self.predict_time(vec)

            all_test_predicts.append(ans)
            all_test_labels.append(label)
        
        return all_test_labels, all_test_predicts


def train_tfidf(train_data, dim=5000, ngram=3, min_df=5):
    ngram_range = (1,3)
    if ngram == 1:
        ngram_range = (1,1)
    elif ngram == 2:
        ngram_range = (1,2)

    tfidf = TfidfVectorizer(
            min_df = min_df,
            max_features = dim,
            ngram_range = ngram_range,
            use_idf = 1,
            smooth_idf = 1
            )
    tfidf.fit(train_data)
    
    return tfidf

def gettime(time):
    #将刑期用分类模型来做
    v = time
    if v == -2:
        return 0
    if v == -1:
        return 1
    elif v > 10 * 12:
        return 2
    elif v > 7 * 12:
        return 3
    elif v > 5 * 12:
        return 4
    elif v > 3 * 12:
        return 5
    elif v > 2 * 12:
        return 6
    elif v > 1 * 12:
        return 7
    else:
        return 8

'''
只反回了第1个label
'''
def read_trainData(path, all_text, accu_label, law_label, time_label, json_labels, json_predicts):
    fin = open(path, 'rb')

    linid = 0
    for line in fin:
        linid += 1
        if linid%5000 == 0:
            print("Process train file at: %d" % linid)
        
        line = line.decode('utf8')
        sample = line2sample(line)
        if None == sample:
            continue

        label, text = sample
        all_text.append(text)
        accu_label.append(label['accusation'][0])
        law_label.append(label['articles'][0])
        time_label.append(gettime(label['imprisonment']))

        ans = {}
        ans['accusation'] = [-1]
        ans['articles'] = [-1]
        ans['imprisonment'] = -3

        json_labels.append(label)
        json_predicts.append(ans)


    fin.close()

    return linid

def read_testData(filename):
    #所有训练文本
    train_data = []
    accu_label = []
    law_label = []
    time_label = []
    train_labels = []
    train_predicts = []

    print('reading train data.')
    train_num = read_trainData(filename, train_data, accu_label, law_label, time_label, train_labels, train_predicts)

    return train_data, train_labels, train_predicts


def f1_func(ground_truth, predictions):
    micro_f1 = f1_score(ground_truth, predictions, average='micro')
    macro_f1 = f1_score(ground_truth, predictions, average='macro')
    return (micro_f1 + macro_f1) / 2.

def train_SVC(vec, label):
    SVC = LinearSVC(class_weight='balanced')

    #SVC = LinearSVC()
    SVC.fit(vec, label)
    return SVC

def train_Adaboost_SVC(vec, label):
    SVC = LinearSVC()
    bdt_real = AdaBoostClassifier(
            base_estimator=SVC,
            n_estimators=10,
            algorithm='SAMME',
            learning_rate=1)

    #SVC = LinearSVC()
    bdt_real.fit(vec, label)
    return bdt_real 


'''
    parameters = {
        'tfidf__max_df': [0.75],   #过滤了几十个词
        'tfidf__min_df': [5],
        'tfidf__max_features': [200000],
        #'tfidf__max_features': (50000, 100000, 200000, 400000),
        'tfidf__ngram_range': [(1, 3)],  # unigrams or trigrams,  use trigrams
        'tfidf__use_idf': [1],
        'tfidf__norm': ('l1', 'l2'),
        'clf__max_iter': [1000],
        'clf__C': (0.1, 0.5, 1.0, 2.0),
        'clf__class_weight':('balanced', None),
        'clf__solver': ('sag', 'liblinear'),
        #'clf__n_iter': (10, 50, 80),
    }
'''

'''
把参数列表 转为任务表的形式。
转为如下任务参数列表：
[任务名, {参数名，参数值}]
'''
def parse_params(parameters):
    all_plist = [[]]
    for key, values in parameters.items():
        cur_plist = list(all_plist)
        all_plist = []

        for val in values:
            for p in cur_plist:
                p_new = list(p)
                p_new.append((key,val))
                all_plist.append(p_new)
    
    params = []
    for plist in all_plist:
        cdict = {}
        for p,v in plist:
            step_name, param_name = p.split('__')
            param_dict = cdict.setdefault(step_name, {})
            param_dict[param_name] = v 

        params.append(cdict)

    return params

def sigint_handler(signum, frame):
    print('Signal handler called with signal %d'%signum)
    raise IOError("Couldn't open device!")
    g_pool.terminate()


global g_pool
if __name__ == '__main__':
    import logging
    logfilename="train.log"
    logger = create_logger(None)

    train_fname = sys.argv[1]
    val_filename = sys.argv[2]
    test_filename = sys.argv[3]
    seg_method = sys.argv[4]
    clf_name = sys.argv[5]

    #train
    print('reading train data...')
    sys.stdout.flush()
    
    #所有训练文本
    train_data = []
    accu_label = []
    law_label = []
    time_label = []
    train_labels = []
    train_predicts = []

    print('reading train data.')
    train_num = read_trainData(train_fname, train_data, accu_label, law_label, time_label, train_labels, train_predicts)
    
    print('reading val data.')
    val_data, val_labels, val_predicts = read_testData(val_filename)

    print('reading test data...')
    sys.stdout.flush()
    test_data, test_labels, test_predicts = read_testData(test_filename)
    
    #for LR
    LR_parameters = {
        'tfidf__max_df': [0.95],   #过滤了几十个词
        'tfidf__min_df': [10, 20],
        'tfidf__max_features': [200000, 400000],
        #'tfidf__max_features': (50000, 100000, 200000, 400000),
        'tfidf__ngram_range': [(1, 3)],  # unigrams or trigrams,  use trigrams
        'tfidf__use_idf': [1],
        'tfidf__norm': ('l1', 'l2'),
        'clf__max_iter': [1000],
        'clf__C': (0.1, 0.5, 1.0, 2.0),
        'clf__class_weight':('balanced', None),
        'clf__solver': ('sag', 'liblinear'),
        #'clf__cv':ps,
        #'clf__n_iter': (10, 50, 80),
    }
    lr_param_list = parse_params(LR_parameters)

    #for SVC
    SVC_parameters = {'tfidf__max_df': [0.95],   #保留全部词差不多是最好的。或者留着0.95
        'tfidf__min_df': (5, 10, 20),
        'tfidf__max_features': (200000, 400000), #去掉了600000. 和40万差不多
        'tfidf__ngram_range': [(1, 3)],  # unigrams or trigrams,  use trigrams
        'tfidf__use_idf': [1],
        'clf__C': (0.1, 0.5, 1.0, 2.0),
        'clf__class_weight':('balanced', None),
        #'clf__n_iter': (10, 50, 80),
    }
    svc_param_list = parse_params(SVC_parameters)

    #for SGD
    SGD_parameters = {
        'tfidf__max_df': [0.95],   #过滤了几十个词
        'tfidf__min_df': (10, 20),
        'tfidf__max_features': (50000, 200000, 400000, 600000),
        'tfidf__ngram_range': [(1, 1), (1, 3)],  # unigrams or trigrams,  use trigrams
        'tfidf__use_idf': [1],
        'tfidf__norm': ('l1', 'l2'),
        'clf__alpha': (0.00001, 0.000005, 0.000001),
        'clf__penalty': ('l2', 'elasticnet'),
        #'clf__n_iter': (10, 50, 80),

    }
    sgd_param_list = parse_params(SGD_parameters)
    
    law_model = None
    accu_model = None
    time_model = None

    '''
    test_fold = np.zeros((train_docs_num + val_docs_num), dtype='int')
    test_fold[:train_docs_num] = -1
    ps = PredefinedSplit(test_fold = test_fold)
    '''
    judge = Judger("../baseline/accu.txt", "../baseline/law.txt")
   
    parameters = SVC_parameters
    param_list = parse_params(parameters)

    def pipeline_train(pid):
        clf = None
        param = None
        if clf_name == 'SVC':
            param = svc_param_list[pid]
            clf = LinearSVC(**param['clf'])
        elif clf_name == 'SGD':
            param = sgd_param_list[pid]
            clf = SGDClassifier(**param['clf'])
        elif clf_name == 'LR':
            param = lr_param_list[pid]
            clf = LogisticRegression(**param['clf'])

        param_str = json.dumps(param)
        tfidf = TfidfVectorizer(**param['tfidf'])
        pipeline = Pipeline([
            ('tfidf', tfidf),
            ('clf', clf),
        ])
        
        beg_time = time()
        pipeline.fit(train_data, accu_label)
        fit_time = time()

        def predict_rst(data, labels, _predicts):
            preds = pipeline.predict(data)
            for i in xrange(len(preds)):
                lab = preds[i]
                _predicts[i]['accusation'] = [lab]

            result = judge.test2(labels, _predicts)
            #print(result)
            rst = judge.get_score(result)

            rstr = '{"ACCU": [%.4f, %.4f, %.4f], "LAW":[%.4f, %.4f, %.4f], "TIME": %.4f}'% \
                (rst[0][0], rst[0][1], rst[0][2], rst[1][0], rst[1][1], rst[1][2], rst[2]) 

            return rst, rstr
        

        train_rst, train_rst = predict_rst(train_data, train_labels, train_predicts) 
        test_rst,test_rstr = predict_rst(test_data, test_labels, test_predicts)
        predit_time = time()

        ptm = int(predit_time - fit_time)
        ftm = int(fit_time - beg_time)
        cur_tm_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        sinfo = '[%s] TrainFile: %s\tSeg: %s\tModel: %s\tParam: %s\t'\
                'Train_Time: %d\tTest_Time: %d\tTrain_Result: %s\tTest_Result: %s'\
                % (cur_tm_str, train_fname, seg_method, clf_name, param_str, ftm, ptm, train_rst, test_rstr)

        lock_fp = open('params.lst') 
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)

        rst_fp = open('train_rst.lst', 'a')
        rst_fp.write(sinfo + '\n')
        rst_fp.flush()
        rst_fp.close()
        #time.sleep(2.)

        lock_fp.close()
        
        logger.info(sinfo)

    #执行训练的主循环
    while True:
        t0 = time()
        param_id = 0
        lock_fp = open('params.lst')
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX)
        try:
            pid_fp = open('param.lineid', 'r')
            lines = pid_fp.readlines()
            pid_fp.close()
            if len(lines) > 0:
                param_id = int(lines[-1].strip()) + 1
        except IOError:
            pass

        if param_id >= len(param_list):
            break

        pid_fp = open('param.lineid', 'a')
        pid_fp.write(str(param_id) + '\n')
        pid_fp.flush()
        pid_fp.close()
        #time.sleep(2.)

        lock_fp.close()
        
        print("Process pid: %d" % param_id)

        pipeline_train(param_id)

        print("done in %0.3fs" % (time() - t0))
        

