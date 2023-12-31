import numpy as np
import pandas as pd
import requests
from io import BytesIO
import joblib
from collections import defaultdict
import tabulate


def load_data():

    url_item_tr = 'https://raw.githubusercontent.com/maegm/content-based-filtering/master/data/content_item_train.csv'
    item_train = pd.read_csv(url_item_tr, header=None).to_numpy()

    url_user_tr = 'https://raw.githubusercontent.com/maegm/content-based-filtering/master/data/content_user_train.csv'
    user_train = pd.read_csv(url_user_tr, header=None).to_numpy()

    url_y_train = 'https://raw.githubusercontent.com/maegm/content-based-filtering/master/data/content_y_train.csv'
    y_train = pd.read_csv(url_y_train, header=None).to_numpy()
    y_train = y_train.reshape((len(y_train),))

    url_item_feat = 'https://raw.githubusercontent.com/maegm/content-based-filtering/master/data/content_item_train_header.txt'
    item_features = pd.read_csv(url_item_feat, header=None).T[0].to_list()

    url_user_feat = 'https://raw.githubusercontent.com/maegm/content-based-filtering/master/data/content_user_train_header.txt'
    user_features = pd.read_csv(url_user_feat, header=None).T[0].to_list()

    url_item_vecs = 'https://raw.githubusercontent.com/maegm/content-based-filtering/master/data/content_item_vecs.csv'
    item_vecs = pd.read_csv(url_item_vecs, header=None).to_numpy()

    url_movies = 'https://raw.githubusercontent.com/maegm/content-based-filtering/master/data/content_movie_list.csv'
    movie_dict = (
        pd.read_csv(url_movies)
        .set_index('movieId')
        .to_dict('index')
    )

    url_gnr = 'https://raw.githubusercontent.com/maegm/content-based-filtering/master/data/content_user_to_genre.pickle'
    r = requests.get(url_gnr)
    user_to_genre = joblib.load(BytesIO(r.content))

    return item_train, user_train, y_train, item_features, user_features, item_vecs, movie_dict, user_to_genre


def pprint_train(x_train, features, maxcount=5):
    """ Prints user_train or item_train nicely """
    df = pd.DataFrame(x_train, columns=features).head(maxcount)
    return df


def split_str(ifeatures, smax):
    ofeatures = []
    for s in ifeatures:
        if ' ' not in s:  # skip string that already have a space
            if len(s) > smax:
                mid = int(len(s) / 2)
                s = s[:mid] + " " + s[mid:]
        ofeatures.append(s)
    return ofeatures


def print_pred_movies(y_p, item, movie_dict, maxcount=10):
    """ print results of prediction of a new user. inputs are expected to be in
        sorted order, unscaled. """
    count = 0
    movies_listed = defaultdict(int)
    disp = [["y_p", "movie id", "rating ave", "title", "genres"]]

    for i in range(0, y_p.shape[0]):
        if count == maxcount:
            break
        count += 1
        movie_id = item[i, 0].astype(int)
        if movie_id in movies_listed:
            continue
        movies_listed[movie_id] = 1
        disp.append([
            y_p[i, 0],
            item[i, 0].astype(int),
            item[i, 2].astype(float),
            movie_dict[movie_id]['title'],
            movie_dict[movie_id]['genres']
        ])

    table = tabulate.tabulate(disp, tablefmt='html', headers="firstrow")
    return table


def gen_user_vecs(user_vec, num_items):
    """ given a user vector return:
        user predict maxtrix to match the size of item_vecs """
    user_vecs = np.tile(user_vec, (num_items, 1))
    return user_vecs


# predict on  everything, filter on print/use
def predict_uservec(user_vecs, item_vecs, model, u_s, i_s, scaler, ScalerUser, ScalerItem, scaledata=False):
    """ given a user vector, does the prediction on all movies in item_vecs returns
        an array predictions sorted by predicted rating,
        arrays of user and item, sorted by predicted rating sorting index
    """
    if scaledata:
        scaled_user_vecs = ScalerUser.transform(user_vecs)
        scaled_item_vecs = ScalerItem.transform(item_vecs)
        y_p = model.predict([scaled_user_vecs[:, u_s:], scaled_item_vecs[:, i_s:]])
    else:
        y_p = model.predict([user_vecs[:, u_s:], item_vecs[:, i_s:]])
    y_pu = scaler.inverse_transform(y_p)

    if np.any(y_pu < 0):
        print("Error, expected all positive predictions")
    sorted_index = np.argsort(-y_pu, axis=0).reshape(-1).tolist()  # negate to get largest rating first
    sorted_ypu = y_pu[sorted_index]
    sorted_items = item_vecs[sorted_index]
    sorted_user = user_vecs[sorted_index]
    return sorted_index, sorted_ypu, sorted_items, sorted_user


def get_user_vecs(user_id, user_train, item_vecs, user_to_genre):
    """ given a user_id, return:
        user train/predict matrix to match the size of item_vecs
        y vector with ratings for all rated movies and 0 for others of size item_vecs """

    if user_id not in user_to_genre:
        print("error: unknown user id")
        return None
    else:
        user_vec_found = False
        for i in range(len(user_train)):
            if user_train[i, 0] == user_id:
                user_vec = user_train[i]
                user_vec_found = True
                break
        if not user_vec_found:
            print("error in get_user_vecs, did not find uid in user_train")
        num_items = len(item_vecs)
        user_vecs = np.tile(user_vec, (num_items, 1))

        y = np.zeros(num_items)
        for i in range(num_items):  # walk through movies in item_vecs and get the movies, see if user has rated them
            movie_id = item_vecs[i, 0]
            if movie_id in user_to_genre[user_id]['movies']:
                rating = user_to_genre[user_id]['movies'][movie_id]
            else:
                rating = 0
            y[i] = rating
    return user_vecs, y


def get_item_genre(item, ivs, item_features):
    offset = np.where(item[ivs:] == 1)[0][0]
    genre = item_features[ivs + offset]
    return genre, offset


def print_existing_user(y_p, y, user, items, item_features, ivs, uvs, movie_dict, maxcount=10):
    """ print results of prediction a user who was in the datatbase. inputs are expected to be in sorted order,
    unscaled. """
    disp = [["y_p", "y", "user", "user genre ave", "movie rating ave", "title", "genres"]]
    count = 0
    for i in range(0, y.shape[0]):
        if y[i, 0] != 0:
            if count == maxcount:
                break
            count += 1
            movie_id = items[i, 0].astype(int)

            offset = np.where(items[i, ivs:] == 1)[0][0]
            genre_rating = user[i, uvs + offset]
            genre = item_features[ivs + offset]
            disp.append([y_p[i, 0], y[i, 0],
                         user[i, 0].astype(int),  # userid
                         genre_rating.astype(float),
                         items[i, 2].astype(float),  # movie average rating
                         movie_dict[movie_id]['title'], genre])

    table = tabulate.tabulate(disp, tablefmt='html', headers="firstrow", floatfmt=[".1f", ".1f", ".0f", ".2f", ".2f"])
    return table
