import os
import sys
import numpy as np
import pandas as pd

from collections import Counter

from sklearn import svm
from sklearn.cluster import KMeans
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.multiclass import OneVsOneClassifier, OneVsRestClassifier

from StockSVM import StockSVM

class Stock:

    def __init__(self, ticker, considerOHL = False, remVolZero = True, train_test_data = False, train_size = 0.8):
        self.__considerOHL__ = considerOHL
        self.__db_dir__ = 'db/stocks'
        self.__OHL__  = []
        self.__default_columns__ = ['Date','Close','High','Low','Open','Volume']
        self.__train_test_data__ = train_test_data
        self.__mapDayIdExtraTreesClf__ = dict()
        self.modelExtraTreesClf = []
        self.extraTreesFeatures = []
        self.indicators_list = []
        self.clf = None
        self.stockSVMs = []
        self.available_labels = []

        if not considerOHL:
            self.__OHL__ = ['Open','High','Low']

        self.__readTicker__(ticker)
        self.df.set_index('Date', inplace = True)

        self.__delExtraColumns__()

        if 'Volume' in self.df.columns and remVolZero:
            self.df = self.df[self.df['Volume'] != 0]

        self.__default_main_columns__ = self.df.columns.tolist()

        if self.__train_test_data__:
            if train_size <= 0 or train_size >= 1:
                print('train_size param must be in (0,1) interval!')
                sys.exit()
            self.train_size = train_size
            self.test = None
            self.test_pred = []
    
    def __repr__(self):
        return self.df.__repr__()

    def __str__(self):
        return self.df.__str__()

    # * Read data stock from file
    def __readTicker__(self, ticker):
        if 'TSLA' in ticker:
            self.df = pd.read_csv('db' + '/{0}.csv'.format(ticker), parse_dates = True)
        else:
            try:
                self.df = pd.read_csv(self.__db_dir__ + '/{0}/{1}.csv'.format(ticker[0].upper(), ticker), parse_dates = True)
            except FileNotFoundError as e:
                print(e)
                sys.exit()

    # * Delete extra columns
    def __delExtraColumns__(self):
        for col in [col for col in self.df.columns if col not in self.__default_columns__]:
            self.df.pop(col)
            print(col + " extra column removed!")

    # * Add predict_next_k_day array to respective stockSVM
    def __add_PredictNxtDay_to_SVM__(self, k_days):
        print("In fit ksvm extraTreesClf add predict SVM")
        if self.stockSVMs != []:
            for label in range(max(self.df['labels']) + 1):
                predict_k_days_col = self.df['predict_' + str(k_days) + '_days']
                predict_k_days_col = predict_k_days_col[self.df['labels'] == label].values
                self.stockSVMs[label].addPredictNext_K_Days(k_days, predict_k_days_col)

    def __set_available_labels__(self):
        for k in self.df['labels']:
            if k not in self.available_labels:
                self.available_labels.append(k)

    # * Split data in train and test data
    def __train_test_split__(self, df = None, extraTreesClf = False, predictNext_k_day = None, extraTreesFirst = 0.2):
        split = int(self.train_size * len(self.df))

        self.df, self.test = self.df[:split], self.df[split:]

        if not extraTreesClf:
            self.test = self.test[['Close'] + self.indicators_list]
        else:
            print("In train split")
            if df is None:
                print("df cannot be None if extraTreesClf is True!")
                sys.exit()
            if predictNext_k_day is None:
                print("predictNext_k_day cannot be None if extraTreesClf is True!")
                sys.exit()

            i = self.__mapDayIdExtraTreesClf__[predictNext_k_day]
            splitFirst = int(len(self.extraTreesFeatures[i])*extraTreesFirst)
            features = [feature[0] for feature in self.extraTreesFeatures[i][:splitFirst]]
            print(len(features))
            self.test = self.df[['Close'] + features]
            print(len(self.test.columns))

        # allowed_list = self.indicators_list
        # if not self.__considerOHL__:
        #     default = set(self.__OHL__ + ['Close','Volume'])
        #     allowed_list = [col for col in allowed_list if col not in default]

    # * Remove rows which has at least one NA/NaN/NULL value
    def removeNaN(self):
        self.df.dropna(inplace = True)

    # * Extremely Randomized Tree Classifier algorithm
    def __fit_ExtraTreesClassifier__(self, features, targets, predictNext_k_day, n_estimators = 10, random_state = None):
        if predictNext_k_day not in self.__mapDayIdExtraTreesClf__.keys():
            self.__mapDayIdExtraTreesClf__[predictNext_k_day] = len(self.__mapDayIdExtraTreesClf__)

            self.modelExtraTreesClf.append(ExtraTreesClassifier(n_estimators = n_estimators,
                                                                n_jobs = -1,
                                                                random_state = random_state))
        else:
            i = self.__mapDayIdExtraTreesClf__[predictNext_k_day]
            self.modelExtraTreesClf[i] = ExtraTreesClassifier(n_estimators = n_estimators,
                                                              n_jobs = -1,
                                                              random_state = random_state)
        i = self.__mapDayIdExtraTreesClf__[predictNext_k_day]
        self.modelExtraTreesClf[i].fit(features, targets)

    # * Apply Extra Trees clf to the features
    def applyExtraTreesClassifier(self, predictNext_k_day,
                                        n_estimators = 10,
                                        random_state = None,
                                        extraTreesFirst = 0.2):
        if extraTreesFirst < 0 or extraTreesFirst > 1:
            print('extraTressFirsts param must be in (0,1) interval!')
            sys.exit()
        self.extraTreesFirst = extraTreesFirst

        self.targets = None
        found_target = False
        for col in self.df.columns:
            if 'predict' in col:
                col_split = col.split('_') # Split predict_k_days column

                # Check if predictNext_k_day day is already applied
                if int(col_split[1]) == predictNext_k_day:
                    self.targets = self.df[col].values
                    found_target = True
                    break
        
        if not found_target:
            self.applyPredict(predictNext_k_day, addPredictDaySVM = False)
            self.targets = self.df['predict_' + str(predictNext_k_day) + '_days'].values
        
        self.targets = self.targets[~np.isnan(self.targets)]

        # Remove rows correspondent to NaN values in targets already removed above
        if self.__train_test_data__:
            self.features = self.df[self.indicators_list].iloc[predictNext_k_day-1:]
        else:
            self.features = self.df[self.indicators_list].iloc[predictNext_k_day-1:-predictNext_k_day]
        
        self.__fit_ExtraTreesClassifier__(self.features, self.targets, predictNext_k_day, n_estimators = n_estimators, random_state = random_state)

        # Sort features based in its importances
        i = self.__mapDayIdExtraTreesClf__[predictNext_k_day]
        self.features = {k : w for k,w in zip(self.indicators_list, self.modelExtraTreesClf[i].feature_importances_)}
        self.features = sorted(self.features.items(), key = lambda x: x[1], reverse = True)

        split_size = int(len(self.features))
        if len(self.modelExtraTreesClf) > len(self.extraTreesFeatures):
            self.extraTreesFeatures.append(self.features[:split_size])
        else:
            self.extraTreesFeatures[i] = self.features[:split_size]

    # * Apply indicators
    def applyIndicators(self, ind_funcs_params, replaceInf = True, remNaN = True):
        for func_param in ind_funcs_params:
            if func_param[1] != None:
                func_param[0](self.df, *func_param[1])
            else:
                func_param[0](self.df)
            print(func_param[0].__name__ + " indicator calculated!")
        
        default = set(self.__default_main_columns__)
        self.indicators_list = [col for col in self.df.columns if col not in default and 'predict' not in col]

        # Replace infinity values by NaN
        if replaceInf:
            self.df.replace([np.inf, -np.inf], np.nan, inplace = True)
        
        # Remove rows which has at least one NA/NaN/NULL value 
        if remNaN:
            self.df.dropna(inplace = True)
        
        if self.__train_test_data__:
            self.__train_test_split__()
    
    # * Say if all clusters has at least num_clusters items
    def __consistent_clusters__(self, num_clusters, labels):
        freqs = Counter(labels).values()
        for freq in Counter(labels).values():
            print(freq)
            if freq <= num_clusters:
                return False
        if min(freqs) / max(freqs) < 0.02:
            return False
        return True

    # * K-Means algorithm
    def __fit_KMeans__(self, df, num_clusters = 5, random_state_kmeans = None):
        self.clf = KMeans(n_clusters = num_clusters,
                          init = 'k-means++',
                          algorithm = 'full',
                          n_jobs = -1,
                          random_state = random_state_kmeans)
        self.clf = self.clf.fit(df.values)
        
        return self.clf.predict(df.values)

    # * Multiclass classifier algorithm
    def __fit_Multiclass_Classifier__(self, df, classifier, random_state_clf, labels):
        if classifier == 'OneVsOne':
            self.clf = OneVsOneClassifier(
                                            svm.LinearSVC(random_state = random_state_clf))\
                                            .fit(df.values, labels)
        elif classifier == 'OneVsRest':
            self.clf = OneVsRestClassifier(
                                            svm.LinearSVC(random_state = random_state_clf))\
                                            .fit(df.values, labels)
        else:
            print('Invalid input classifier!')
            sys.exit()
        
        return self.clf.predict(df.values)

    # * K-SVMeans clustering
    def fit_kSVMeans(self, num_clusters = 5, 
                           classifier = 'OneVsOne',
                           random_state_kmeans = None,
                           random_state_clf = None,
                           consistent_clusters_kmeans = False,
                           consistent_clusters_multiclass = False,
                           extraTreesClf = False,
                           predictNext_k_day = None,
                           extraTreesFirst = 0.2):
        
        if extraTreesClf:
            if predictNext_k_day is None or predictNext_k_day <= 0:
                print("predictNext_k_day must be greater than 0 when extraTreesClf is True!")
                sys.exit()
            elif predictNext_k_day not in self.__mapDayIdExtraTreesClf__.keys():
                print("ExtraTrees model for predict {0} days not fitted yet!".format(predictNext_k_day))
                sys.exit()
            else:
                i = self.__mapDayIdExtraTreesClf__[predictNext_k_day]
                split = int(len(self.extraTreesFeatures[i])*0.2)
                self.features2 = [feature[0] for feature in self.extraTreesFeatures[i][:split]]
                self.df2 = self.df[['Close'] + self.features2]
        else:
            self.df2 = self.df[['Close'] + self.indicators_list]

        # self.df2 = self.df.copy()
        # for col in self.df2.columns:
        #     if col in self.__OHL__ + ['Volume']:
        #         self.df2 = self.df2.drop(col, axis = 1)
        #     elif 'predict' in col:
        #         self.df2 = self.df2.drop(col, axis = 1)
        #     elif 'labels' in col:
        #         self.df2 = self.df2.drop(col, axis = 1)
        
        labels = self.__fit_KMeans__(self.df2, num_clusters = num_clusters, random_state_kmeans = random_state_kmeans)

        self.df['labels_kmeans'] = labels
        
        if consistent_clusters_kmeans:
            print('KMeans')
            while not self.__consistent_clusters__(num_clusters, labels):
                labels = self.__fit_KMeans__(self.df2, num_clusters = num_clusters, random_state_kmeans = None)
                print()

        if classifier is not None:
            labels_clf = self.__fit_Multiclass_Classifier__(self.df2, classifier = classifier, random_state_clf = random_state_clf, labels = labels)
            if consistent_clusters_multiclass:
                print('Multiclass')
                while not self.__consistent_clusters__(max(labels_clf) + 1, labels_clf):
                    labels_clf = self.__fit_Multiclass_Classifier__(self.df2, classifier = classifier, random_state_clf = None, labels = labels)
                    print()

        if classifier is not None:
            self.df['labels'] = labels_clf
        else:
            self.df['labels'] = labels

        self.__set_available_labels__()

        if extraTreesClf:
            print("In fit ksvm extraTreesClf")
            self.__add_PredictNxtDay_to_SVM__(predictNext_k_day)
            if self.__train_test_data__:
                print("In fit ksvm extraTreesClf train split")
                self.__train_test_split__(df = self.df2,
                                          extraTreesClf = True,
                                          predictNext_k_day = predictNext_k_day,
                                          extraTreesFirst = extraTreesClf)

        # return labels

    # * Apply predict next n days
    def applyPredict(self, k_days = 1, addPredictDaySVM = True):
        if k_days < 1:
            print("k_days must be greater than 0!")
            sys.exit()

        predict_next = [np.nan for k in range(len(self.df.index))]
        if self.__train_test_data__:
            predict_next.extend([np.nan for k in range(len(self.test.index))])

        if k_days == 1:
            prices = self.df['Close'].values
            if self.__train_test_data__:
                prices = np.append(prices, self.test['Close'].values)

            for k in range(len(prices) - 1):
                if prices[k+1] > prices[k]:
                    predict_next[k] = 1
                elif prices[k+1] < prices[k]:
                    predict_next[k] = -1
                else:
                    predict_next[k] = 0
        else:
            if self.__train_test_data__:
                sma = self.df['Close'].append(self.test['Close'])
                sma = sma.rolling(k_days).mean().values
            else:
                sma = self.df['Close'].rolling(k_days).mean().values

            for k in range(k_days - 1, len(sma) - k_days):
                if sma[k + k_days] > sma[k]:
                    predict_next[k] = 1
                elif sma[k + k_days] < sma[k]:
                    predict_next[k] = -1
                else:
                    predict_next[k] = 0
        
        if self.__train_test_data__:
            self.df['predict_' + str(k_days) + '_days'] = predict_next[:len(self.df.index)]
            self.test_pred = predict_next[len(self.df.index):]            
        else:
            self.df['predict_' + str(k_days) + '_days'] = predict_next

        if addPredictDaySVM:
            self.__add_PredictNxtDay_to_SVM__(k_days)

        # return predict_next

    # * Split and return a data frame
    def splitByLabel(self):
        if self.clf is None:
            print('Data must be clusterized before split by label!')
            sys.exit()
        
        self.stockSVMs = []

        for label in range(max(self.df['labels_kmeans'])+1):
            new_stockSVM = self.df[self.df['labels'] == label]

            for col in new_stockSVM.columns:
                if 'predict' in col:
                    new_stockSVM = new_stockSVM.drop(col, axis = 1)
                elif col in self.__OHL__ + ['Volume', 'labels_kmeans', 'labels']:
                    new_stockSVM = new_stockSVM.drop(col, axis = 1)

            new_stockSVM = StockSVM(new_stockSVM)
            self.stockSVMs.append(new_stockSVM)
    
    # * Fit data in each SVM Cluster
    def fit(self, predictNext_k_day, C = 1.0, gamma = 'auto', gridSearch = False, parameters = None, n_jobs = 3, k_fold_num = None, verbose = 1):
        if self.stockSVMs != []:
            for svm in self.stockSVMs:
                if not svm.values.empty:
                    if gridSearch:
                        svm.fitGridSearch(predictNext_k_day = predictNext_k_day,
                                          parameters = parameters,
                                          n_jobs = n_jobs,
                                          k_fold_num = k_fold_num,
                                          verbose = verbose)
                    else:
                        svm.fit(predictNext_k_day, C, gamma)
    
    # * Predict which SVM Cluster df param belongs
    def predict_SVM_Cluster(self, df):
        return self.clf.predict(df)

    def predict_SVM(self, cluster_id, df):

        # Treat if the SVM cluster chosen have no data
        # Predict using larget SVM
        # TODO Create a better solution
        if len(self.stockSVMs[cluster_id].values) == 0:
            biggest = cluster_id
            for k, stockSVM in enumerate(self.stockSVMs):
                lenSVM = len(stockSVM.values)
                if lenSVM > biggest:
                    biggest = lenSVM
                    cluster_id = k

        return self.stockSVMs[cluster_id].predict(df)