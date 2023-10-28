import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

plt.rcParams["axes.spines.top"] = False
plt.rcParams["axes.spines.right"] = False
plt.rcParams.update({"axes.grid": True})
plt.rcParams["grid.linewidth"] = 0.2
plt.rcParams["grid.alpha"] = 0.5


def missings_plot(data):
    
    """
    Creates horizontal bar plots showing the number of missing values and zero values for selected features.

    Parameters:
    -----------
    data : pandas DataFrame
        The input DataFrame containing the data.
    return_features : bool, optional (default=False)
        If True, returns a list of features with missing values.
    """

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 4))

    features_with_nan = [feature for feature in data.columns if data[feature].isnull().sum() > 0]
    number_of_nan_values = [data[feature].isnull().sum() for feature in features_with_nan]

    ax1.barh(features_with_nan, number_of_nan_values, color="steelblue")
    ax1.set_title("Missing values")
    ax1.set_xscale("log")

    for number, feature in zip(number_of_nan_values, features_with_nan):
        ax1.annotate(number,(number, feature),
                     fontsize = 10,
                     va = "center", 
                     ha = "center",
                     bbox = dict(boxstyle="round",
                                 fc = "aliceblue"))

    features_with_zeros = ["Monthly_Income", "Loan_Amount_Applied", "Loan_Tenure_Applied", "Existing_EMI", "Employer_Name"]
    number_of_zero_values = ((data[features_with_zeros] == 0) | (data[features_with_zeros] == "0")).sum()

    ax2.barh(features_with_zeros, number_of_zero_values, color = "lightseagreen")
    ax2.set_title("Zero values")
    ax2.set_xscale("log")

    for number, feature in zip(number_of_zero_values, features_with_zeros):
        ax2.annotate(number, (number, feature),
                     fontsize = 10,
                     va = "center",
                     ha = "center",
                     bbox = dict(boxstyle = "round",
                                 fc = "azure"))

    plt.tight_layout()
    plt.show()


def histplots_grid(n_rows, n_cols, data, features = None):	
    
    """
    Creates a grid of histograms.

    Args:
        n_rows (int): Number of rows in the grid.
        n_cols (int): Number of columns in the grid.
        data (pd.DataFrame): The dataframe containing the data for plotting.
        features (list, optional): List of feature names to plot. 
            If not provided, it selects numeric features with more than 2 unique values.

    Number of rows and columns must correspond with the number of features.
    """

    if features is None:
        features = [feature for feature in data.select_dtypes([int, float]).columns 
                    if data[feature].nunique() > 2]
    
    width = n_cols * 4
    height = n_rows * 3
    
    plt.figure(figsize=(width, height))
    
    for i, feature in enumerate(features):
        plt.subplot(n_rows, n_cols, i + 1)
        plt.hist(data[feature], color="steelblue")
        plt.title(feature)
        plt.locator_params(axis = 'x', nbins = 4)
        plt.locator_params(axis = 'y', nbins = 4)
        
        if feature in ["Monthly_Income", "Existing_EMI"]:
            plt.yscale("log")
        
    plt.tight_layout()    
    plt.show()


def countplots(*args, data):
    
    """
    Creates countplots for one or more categorical features.

    Args:
        *args (str): One or more feature names to create countplots for.
        data (pd.DataFrame): The dataframe containing the data to visualize.
    """

    for feature in args:
        plt.figure(figsize=(15, 3))
        order = data[feature].value_counts().index
        ax = sns.countplot(x = feature,
                           data = data,
                           order = order,
                           palette = "viridis")
        
        ax.set_yscale("log")
        plt.title(f'Distribution of {feature}')

        if len(str(data[feature].unique()[0])) >= 4:
            plt.xticks(rotation = 45)

        for p in ax.patches:
            height = p.get_height()
            ax.annotate(f'{height:.0f}', (p.get_x() + p.get_width() / 2., height),
                        ha = 'center', va = 'bottom', fontsize = 10)

        plt.tight_layout()
        plt.show()


def feature_importance_plot(importances, feature_names, title="Feature Importances"):
    
    """
    Creates horizontal barplot for feature importances.

    Args:
        importances (np.array): Feature importances values.
        feature_names (list): Feature names for plotting.
    """
    
    sorted_indices = importances.argsort()
    sorted_names = [feature_names[i] for i in sorted_indices]
    sorted_importances = importances[sorted_indices]

    plt.figure(figsize=(7, 6))
    plt.barh(range(len(sorted_names)), 
             sorted_importances, 
             align="center", color = "steelblue")
    
    plt.yticks(range(len(sorted_names)), sorted_names)
    plt.xlabel("Feature Importance")
    plt.ylabel("Feature Name")
    plt.title(title)
    plt.tight_layout()
    plt.show()


def thresholds_results_plot(results, thresholds, optimal_thresholds):
    
    """
    Plots precision, recall, and F1 Score for different discrimination thresholds.

    Args:
    results (dict): A dictionary containing results for different estimators.
        Each key-value pair represents the name of an estimator and its corresponding scores.
        The scores includes precision, recall, and F1 Score.
    thresholds (np.array): An array of threshold values.
    optimal_thresholds (list): An array of optimal threshold values corresponding to each estimator.
    """
    
    fig, ax = plt.subplots(2, 2, figsize=(12, 8))
    ax = ax.flatten()

    for i, (estimator_name, scores) in enumerate(results.items()): 

        f1_scores, precision_scores, recall_scores = scores
        max_f1_idx = np.argmax(f1_scores)
        max_f1 = f1_scores[max_f1_idx]

        ax[i].plot(thresholds, precision_scores, color="orange", label="Precision")
        ax[i].plot(thresholds, recall_scores, color="blue", label="Recall")
        ax[i].plot(thresholds, f1_scores, color="green", label="F1 Score")
        ax[i].scatter(thresholds[max_f1_idx], max_f1, c = "darkgreen", label = f"Max F1 = {max_f1:.2f}")

        ax[i].axvline(x=optimal_thresholds[i], color="black", linestyle="--", linewidth=0.8, label=f"Optimal threshold = {optimal_thresholds[i]}")

        ax[i].set_title(estimator_name)
        ax[i].set_xlabel("Threshold")
        ax[i].set_ylabel("Score")
        ax[i].set_xticks(np.arange(0, 1.1, 0.1))
        ax[i].set_yticks(np.arange(0, 1.1, 0.1))
        ax[i].legend()

    plt.tight_layout()
    plt.show()