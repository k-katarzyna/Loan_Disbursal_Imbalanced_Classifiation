import os
from copy import deepcopy
from warnings import filterwarnings, warn
from joblib import Parallel, delayed, dump

import pandas as pd
import numpy as np
from sklearn import set_config
from sklearn.compose import make_column_transformer
from sklearn.feature_selection import SelectFromModel
from sklearn.impute import SimpleImputer
from sklearn.metrics import roc_auc_score, precision_score, recall_score, f1_score
from sklearn.model_selection import (cross_validate, StratifiedKFold, GridSearchCV,
                                     RandomizedSearchCV)
from sklearn.pipeline import make_pipeline, Pipeline
from sklearn.preprocessing import OneHotEncoder, TargetEncoder
from imblearn.metrics import geometric_mean_score

from src.utils import to_labels
from src.visuals import thresholds_results_plot

filterwarnings("ignore")
set_config(transform_output="pandas")


RANDOM_STATE = 42
CV_SCHEME = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
PARAMS_TO_SAVE = ["n_estimators", 
                  "class_weight", 
                  "min_samples_leaf", 
                  "max_samples", 
                  "max_features"]
HANDLE_MISSINGS_MODELS = ["HistGradientBoostingClassifier", 
                          "BaggingClassifier", 
                          "BalancedBagging_OverSampling", 
                          "BalancedBagging_UnderSampling"]


def set_model_params(model, model_params): 
    """
    Set parameters for a given model.

    Args:
        model (object): An object of the machine learning model class. 
        model_params (dict): Dictionary of parameters to be set for the model. 
            These parameters should be hiperparameters or other settings compatible 
            with the model class.

    Returns:
        object: A new instance of the model class with the specified parameters set.
    """
    model_copy = deepcopy(model)
    model_copy.set_params(**model_params)
    
    return model_copy


def create_models(base_models, model_params=None):
    """
    Create a list of models with specified parameters.

    Args:
        base_models (list of objects): List of base machine learning models.
        model_params (list of [lists of dicts or dicts], optional): default=None
            Parameters for each model. Each element can be a dictionary of parameters 
            for the corresponding model in 'base_models' or a list of dictionaries if 
            different parameter sets are needed for the same model type. 
            If None, default parameters with only 'random_state' and 'n_jobs' set 
            (defaults for these are specified by the function) are used.

    Returns:
        list of objects: A list of machine learning models with specified parameters.

    Raises:
        ValueError: If an element of 'model_params' is neither a dictionary nor a list 
            of dictionaries.
    """
    models = [model.set_params(random_state=RANDOM_STATE, n_jobs=-1) 
              if "n_jobs" in model.get_params() 
              else model.set_params(random_state=RANDOM_STATE) 
              for model in base_models]

    if model_params:
        for model, params in zip(models, model_params):
            if isinstance(params, list):
                for param_dict in params:
                    models.append(set_model_params(model, 
                                                   param_dict))
            elif isinstance(params, dict):
                models.append(set_model_params(model, 
                                               params))
            else:
                raise ValueError("Invalid format in model_params list. Each element "
                                 "should be either a dictionary or a list of dictionaries.")
            
    return models


def prepare_models_info(models, params_to_save):    
    """
    Extract model names and selected hyperparameters for a list of machine learning models.

    Args:
        models (list): List of machine learning model objects.
        params_to_save (list): List of hyperparameter names to extract from each model.

    Returns:
        tuple: A tuple of two lists - the first list contains the names of the models, 
            and the second list contains strings representing the values of the 
            hyperparameters specified in 'params_to_save'.
    """
    names = []
    params = []
    
    for model in models:
        model_name = model.__class__.__name__

        if model_name == "BalancedBaggingClassifier":
            if getattr(model, "sampler").__class__.__name__ == "RandomUnderSampler":
                model_name = "BalancedBagging_UnderSampling"
            else:
                model_name = "BalancedBagging_OverSampling"

        model_params = ", ".join([f"{param}: {getattr(model, param)}"
                                  for param in params_to_save
                                  if hasattr(model, param)])
        
        names.append(model_name)
        params.append(model_params)
        
    return names, params


def create_preprocessor(X):
    """
    Extract numerical and categorical features from input data and define a 
    general preprocessor for experiments.

    Args:
        X (pd.DataFrame): The input DataFrame containing data for feature 
        extraction.

    Returns:
        tuple of (list, list, object): 
        - The first list contains the names of numerical features.
        - The second list contains the names of categorical features.
        - The third element is an object representing the general preprocessor 
          configured for the input data.
    """
    num_features = X.select_dtypes("number").columns
    cat_features = X.select_dtypes("object").columns

    general_preprocessor = make_column_transformer((SimpleImputer(strategy="constant",
                                                                  fill_value=-1),
                                                    num_features),
                                                   (TargetEncoder(random_state=RANDOM_STATE),
                                                    cat_features))
    
    return num_features, cat_features, general_preprocessor


def cv_scores(pipeline, X, y, model_name, model_params):
    """
    Calculate cross validation scores and prepare a dictionary with the results.

    Args:
        pipeline (object): A pipeline containing preprocessing steps and a classifier.
        X (pd.DataFrame): Input data.
        y (pd.Series): Target labels.
        model_name (str): Name of the model.
        model_params (str): Model parameters to save.

    Returns:
        dict: Dictionary containing test results.
    """
    cv_results = cross_validate(pipeline, 
                                X, y, 
                                scoring="roc_auc",
                                cv=CV_SCHEME, 
                                n_jobs=-1)
    
    roc_auc = np.round(cv_results["test_score"].mean(), 4)
    time = np.round((cv_results["fit_time"] + cv_results["score_time"]).mean(), 2)

    return {"Model": model_name,
            "Parameters": model_params,
            "ROC_AUC": roc_auc,
            "Time[s]": time}


def create_results_dataframe(*args):
    """
    Create a results dataframe from any number of dictionaries or dataframes.
    
    Args:
        *args(dict or pd.DataFrame): Variable number of elements containing results data.
    
    Returns:
        pd.DataFrame: A DataFrame containing the results.
    """
    if len(args) == 1:
        df = pd.DataFrame(args[0])
    elif len(args) > 1:
        df = pd.concat([pd.DataFrame(arg) for arg in args])
        
    return df


def save_result_data(func):
    """
    Decorator to save the results of a function to specified file paths.

    The decorator extends a function to save its output. It handles both the primary
    results and additional data (if any). The primary results are expected to be
    a pandas DataFrame which is saved to a CSV file. Additional data, if provided,
    is saved to a PKL file. The paths for saving these outputs are specified through
    keyword arguments 'save_results_path' and 'save_additional_results_path'

    Args:
        func (callable): The function whose results are to be saved.

    Returns:
        Callable: A wrapper function that saves the results of the original function.

    Note:
        The decorated function should return a DataFrame as its main result. If it 
        returns a tuple, the first element should be the main DataFrame result and 
        the second element should be the additional data to be saved using joblib.
    """
    def wrapper(*args, **kwargs):
        returned_values = func(*args, **kwargs)

        if isinstance(returned_values, tuple) and len(returned_values) == 2:
            results, additional_results = returned_values
        else:
            results = returned_values
            additional_results = None

        save_results_path = kwargs.get("save_results_path", None)
        save_additional_results_path = kwargs.get("save_additional_results_path", None)

        if save_results_path:
            results.to_csv(save_results_path, index=False)
        else:
            warn("No path provided, the result data won't be saved.")
        
        if additional_results and save_additional_results_path:
            dump(additional_results, save_additional_results_path)

        return results
    return wrapper
        

@save_result_data
def imputation_test(X, y, models, preprocessors, save_results_path=None):
    """
    Perform the imputation test, collect and, optionally, save the results
    for the tested models' scores.

    Args:
        X (pd.DataFrame): Input data.
        y (pd.Series): Target labels.
        models (list): List of models to evaluate.
        preprocessors (list): List of imputing preprocessors.
        save_results_path (str, optional): default=None
            Path for saving results as a CSV file. 
    
    Returns:
        pd.DataFrame: A DataFrame containing the results of the imputation test.
    """
    names, params = prepare_models_info(models, PARAMS_TO_SAVE)
    num_features, cat_features, _ = create_preprocessor(X)
    results = []
    
    for model, model_name, model_params in zip(models, names, params):
        
        for imputer, preprocessor in preprocessors:
            
            if imputer == "none" and model_name not in HANDLE_MISSINGS_MODELS:
                continue
            else:
                preprocessor = make_column_transformer((preprocessor, 
                                                        num_features),
                                                       (OneHotEncoder(sparse_output=False), 
                                                        cat_features))
                pipeline = make_pipeline(preprocessor, model)
                
                result = cv_scores(pipeline,
                                   X, y, 
                                   model_name, 
                                   model_params)

                result["Imputation"] = imputer
                results.append(result)
    
    return create_results_dataframe(results)


def detailed_best_imputation_results(results):
    """
    Display the best ROC_AUC score and its corresponding time for each combination
    of model and imputation method, excluding `KNNImputer` method.

    Args:
        results (pd.DataFrame): A DataFrame containing imputation test results. 

    Returns:
        pandas.io.formats.style.Styler
            A styled DataFrame with models as rows, imputation methods as columns,
            and two sub-columns for each imputation method: 'ROC_AUC' and 'Time[s]'.
            Each cell in the 'ROC_AUC' sub-column contains the maximum ROC_AUC value
            for the corresponding model and imputation method, and each cell in
            the 'Time[s]' sub-column contains the time associated with achieving
            that ROC_AUC score.
    """
    filtered_results = (results[results["Imputation"] != "KNNImputer"]
                        .groupby(["Model", "Imputation"])["ROC_AUC"])
    max_roc_auc = filtered_results.max().reset_index()
    time = results.loc[filtered_results.idxmax(), ["Model", "Imputation", "Time[s]"]]
    
    merged = (pd
              .merge(max_roc_auc,
                     time,
                     on=["Model", "Imputation"],
                     how="left")
              .pivot(index="Model",
                     columns="Imputation",
                     values=["ROC_AUC", "Time[s]"]))
    
    return (merged
            .style
            .background_gradient()
            .apply(lambda x: ["background-color: transparent" if pd.isna(v) else "" for v in x]))


@save_result_data
def cat_encoding_test(X, y, models, preprocessors, save_results_path=None):
    """
    Perform the category encoding test, collect and, optionally, save the results
    for the tested models' scores.

    Args:
        X (pd.DataFrame): Input data.
        y (pd.Series): Target labels.
        models (list): List of models to evaluate.
        preprocessors (list): List of categorical preprocessors.
        save_results_path (str, optional): default=None
            Path for saving results as a CSV file.
    
    Returns:
        pd.DataFrame: A DataFrame containing the results of the category encoding test.
    """
    names, params = prepare_models_info(models, PARAMS_TO_SAVE)
    num_features, cat_features, _ = create_preprocessor(X)
    results = []
    
    for model, model_name, model_params in zip(models, names, params):
    
        for encoder, preprocessor in preprocessors:
            preprocessor = make_column_transformer((SimpleImputer(strategy="constant",
                                                                  fill_value=-1),
                                                    num_features),
                                                   (preprocessor, cat_features))
            pipeline = make_pipeline(preprocessor, model)
            
            result = cv_scores(pipeline,
                               X, y, 
                               model_name, 
                               model_params)
            
            result["Encoder"] = encoder
            results.append(result)
        
    return create_results_dataframe(results)


@save_result_data
def feature_selection_test(X, y, models, estimator, selection_thresholds,
                           save_results_path=None):
    """
    Perform the feature selection test using feature importances, and, optionally,
    save the results for the tested models' scores.

    Args:
        X (pd.DataFrame): Input data.
        y (pd.Series): Target labels.
        models (list): List of models to evaluate.
        estimator: Machine learning model for use as feature selection estimator.
        selection_thresholds (list): List of threshold values for feature selection.
        save_results_path (str, optional): default=None
            Path for saving results as a CSV file.

    Returns:
        pd.DataFrame: A DataFrame containing the results of the feature selection test.
    """
    names, params = prepare_models_info(models, PARAMS_TO_SAVE)
    _, _, preprocessor = create_preprocessor(X)
    results = []
    
    for threshold in selection_thresholds:
        important_features = estimator.feature_importances_ > threshold
        selected = np.round(important_features.mean() * 100)
        rejected = np.where(~important_features)[0]
        
        for model, model_name, model_params in zip(models, names, params):
            pipeline = make_pipeline(preprocessor,
                                     SelectFromModel(estimator=estimator,
                                                     threshold=threshold),
                                     model)
            
            result = cv_scores(pipeline,
                               X, y,
                               model_name,
                               model_params)

            result["Threshold"] = np.round(threshold, 4)
            result["Selected[%]"] = selected
            result["Rejected[idx]"] = rejected
            
            results.append(result)
            
    return create_results_dataframe(results)


def grid_search(X, y, model, param_grid, save_artifact_path):
    """
    Perform a grid search for hyperparameter optimization on a given model,
    save the best model and display the best score.

    Args:
        X (pd.DataFrame): The input features.
        y (pd.Series): The target labels.
        model: The machine learning model.
        param_grid (dict): The grid of hyperparameters to search.
        save_artifact_path (str): Path to save the best model as a PKL file.

    Returns:
        float: The best ROC AUC score achieved during grid search.
    """
    _, _, preprocessor = create_preprocessor(X)
        
    pipeline = Pipeline([
        ("preprocessor", preprocessor),
        ("model", model)
    ])

    optimizer = GridSearchCV(pipeline, 
                             param_grid, 
                             cv=CV_SCHEME, 
                             scoring="roc_auc", 
                             n_jobs=-1)
    optimizer.fit(X, y)

    dump(optimizer.best_estimator_.steps[1][1], save_artifact_path)

    return np.round(optimizer.best_score_, 4)


@save_result_data
def randomized_search(X, y, 
                      models, grids, 
                      preprocessors, 
                      n_iter, 
                      save_artifact_folder, 
                      save_results_path=None, 
                      save_additional_results_path=None):
    """
    Perform a randomized search with cross-validation for hyperparameter optimization
    across a list of models, saving the best results and estimators, and a dictionary
    of mean test scores for analysis. Saving result data is optional.

    Args:
        X (pd.DataFrame): The input features.
        y (pd.Series): The target labels.
        models (list of objects): List of machine learning models.
        grids (list of dicts): List of hyperparameter grids corresponding to each model.
        preprocessors (list): List of preprocessors for feature engineering.
        n_iter (int): Number of iterations for randomized search.
        save_artifact_folder (str): Folder path to save the best models as PKL files.
        save_results_path (str, optional): default=None
            Path to save the best results as a CSV file.
        save_additional_results_path (str, optional): default=None
            Path to save dictionary with mean test scores as a PKL file.

    Returns:
        pd.DataFrame: A DataFrame containing the ranking of models after optimization.
    """
    results = []
    test_scores = {}

    for model, param_grid in zip(models, grids):
        pipeline = Pipeline([
            ("preprocessor", preprocessors[0]),
            ("remover", preprocessors[1]),
            ("model", model)
        ])

        optimizer = RandomizedSearchCV(pipeline, 
                                       param_grid,
                                       n_iter=n_iter,
                                       cv=CV_SCHEME,
                                       scoring="roc_auc",
                                       n_jobs=-1, 
                                       error_score="raise")
        optimizer.fit(X, y)

        model_name = model.__class__.__name__
        roc_auc = np.round(optimizer.best_score_, 4)
        
        test_scores[model_name] = optimizer.cv_results_["mean_test_score"]
        
        idx = np.where(optimizer.cv_results_["rank_test_score"] == 1)
        time = np.round((optimizer.cv_results_["mean_fit_time"] 
                         + optimizer.cv_results_["mean_score_time"])[idx][0], 2)

        result = {"Model": model_name,
                  "ROC_AUC": roc_auc,
                  "Time[s]": time}

        results.append(result)

        artifact_path = os.path.join(save_artifact_folder, model_name + ".pkl")
        dump(optimizer.best_estimator_, artifact_path)
    
    return create_results_dataframe(results), test_scores


def load_results_from_folder(folder_path, columns_to_select):
    """
    Load results from CSV files in a given folder and create a summary DataFrame.

    Args:
        folder_path (str): Path to the folder containing CSV files.
        columns_to_select (list): List of column names to select from each CSV file.

    Returns:
        pd.DataFrame: A DataFrame containing the selected columns from loaded CSV files.
    """
    results = []
    
    for file_name in os.listdir(folder_path):
        if file_name.endswith(".csv"):
            file_path = os.path.join(folder_path, file_name)
            result_df = pd.read_csv(file_path)[columns_to_select]
            results.append(result_df)
  
    return create_results_dataframe(*results)


def summarize_results(results_df, column_to_group_by, folder_path=None):
    """
    Display summary statistics for a DataFrame grouped by a specified column.

    The function takes a DataFrame and a column name as input and computes summary
    statistics (count, max, mean, min) for two specified columns ('ROC_AUC' and 'Time[s]')
    after grouping the DataFrame by the specified column. Returns a styled DataFrame
    with background gradient applied to the 'mean_roc_auc', 'max_roc_auc', 'mean_time[s]'
    and 'max_time[s]' columns.

    Args:
        results_df (pd.DataFrame or str): The input DataFrame containing the data to be
            summarized. If a string 'all_results' is provided, the function needs also
            folder_path to be given and reads data from CSV files and creates a summary
            DataFrame.
        column_to_group_by (str): The name of the column by which the DataFrame should
            be grouped.
        folder_path (str, optional): default=None
            To use only with results_df == 'all_results', provides the folder path where
            files to concat and summarize are located.

    Returns:
        pandas.io.formats.style.Styler
            A styled DataFrame with summary statistics and background gradient for specific
            columns.
    """
    if isinstance(results_df, str) and results_df == "all_results":  
        columns_to_select = ["Model", "ROC_AUC", "Time[s]"]
        results_df = load_results_from_folder(folder_path, columns_to_select)
   
    results = (results_df
               .groupby(column_to_group_by)
               .agg(
                   {"ROC_AUC": [np.size, np.max, np.mean, np.min],
                    "Time[s]": [np.mean, np.min, np.max]
                    })
               .set_axis(["count", "max_roc_auc", "mean_roc_auc", "min_roc_auc", 
                          "mean_time[s]", "min_time[s]", "max_time[s]"],
                         axis=1)
               .round(4))

    results["mean_time[s]"] = results["mean_time[s]"].round(2)
    results = results.sort_values(by=["max_roc_auc", "mean_roc_auc"], 
                                  ascending=False)

    return results.style.background_gradient(subset=["max_roc_auc", "mean_roc_auc", 
                                                     "mean_time[s]", "max_time[s]"])


def process_fold(train_idx, test_idx, X, y, estimator):
    """
    Process a single fold of cross-validation as part of the
    `evaluate_discrimination_thresholds` function. Provide training and testing sets
    for the fold using given indices and calculate the probabilities of positive class
    predictions.
    
    Args:
        train_idx (np.array): Indices of the training data.
        test_idx (np.array): Indices of the testing data.
        X (pd.DataFrame): The input data.
        y (pd.Series): The target labels.
        estimator (object) : Estimator for fitting and estimating probabilities.

    Returns:
        y_test (pd.Series): True labels for the testing set.
        y_proba (np.array): Estimated probabilities for the positive class per fold.
    """
    X_train, X_test, y_train, y_test = (X.iloc[train_idx],
                                        X.iloc[test_idx],
                                        y.iloc[train_idx],
                                        y.iloc[test_idx])

    estimator_copy = deepcopy(estimator)
    estimator_copy.fit(X_train, y_train)
    y_proba = estimator_copy.predict_proba(X_test)[:, 1]

    return y_test, y_proba


def evaluate_discrimination_thresholds(estimators, X, y, thresholds):
    """
    Perform parallel cross-validation for multiple estimators, saving the probabilities
    for each split. Then, calculate metrics (F1, precision, recall and geometric mean)
    across a range of specified discrimination thresholds and plot the results using
    the `thresholds_results_plot` function. This includes marking the best F1 score
    and identifying the optimal classification threshold.

    Args:
        estimators (list of tuples): List of (estimator_name, estimator object) pairs.
        X (pd.DataFrame): The input features.
        y (pd.Series): The target labels.
        thresholds (np.array): List of threshold values to evaluate.

    Returns:
        results (dict): A dictionary of results for each estimator.
        optimal_thresholds (list): List of optimal threshold values.
    """
    results = {}
    optimal_thresholds = []

    X, y = X.copy(), y.copy()

    X.reset_index(drop=True, inplace=True)
    y.reset_index(drop=True, inplace=True)

    for estimator_name, estimator in estimators:
        f1_scores = []
        precision_scores = []
        recall_scores = []
        g_mean_scores = []
        
        results_per_fold = Parallel(n_jobs=-1)(
            delayed(process_fold)(train_idx, test_idx, X, y, estimator)
            for train_idx, test_idx in CV_SCHEME.split(X, y)
            )

        for threshold in thresholds:
            f1_cv = []
            precision_cv = []
            recall_cv = []
            g_mean_cv = []

            for y_test, y_proba in results_per_fold:
                y_pred = to_labels(y_proba, threshold)
                
                f1 = f1_score(y_test, y_pred)
                precision = precision_score(y_test, y_pred)
                recall = recall_score(y_test, y_pred)
                g_mean = geometric_mean_score(y_test, y_pred)
                
                f1_cv.append(f1)
                precision_cv.append(precision)
                recall_cv.append(recall)
                g_mean_cv.append(g_mean)

            f1_scores.append(np.mean(f1_cv))
            precision_scores.append(np.mean(precision_cv))
            recall_scores.append(np.mean(recall_cv))
            g_mean_scores.append(np.mean(g_mean_cv))

        optimal_threshold = thresholds[np.argmax(g_mean_scores)]
        optimal_thresholds.append(optimal_threshold)

        results[estimator_name] = (f1_scores, precision_scores,
                                   recall_scores, g_mean_scores)

    thresholds_results_plot(results, thresholds, optimal_thresholds)

    return results, optimal_thresholds