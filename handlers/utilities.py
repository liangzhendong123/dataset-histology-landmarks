"""
General utils used for this collection of scripts

Copyright (C) 2014-2018 Jiri Borovec <jiri.borovec@fel.cvut.cz>
"""


import os
import re
import glob
import logging
import multiprocessing as mproc

import tqdm
import numpy as np
import pandas as pd
import matplotlib.pylab as plt

NB_THREADS = max(1, int(mproc.cpu_count() * 0.9))
SCALES = (5, 10, 25, 50, 100)
# template nema for scale folder
TEMPLATE_FOLDER_SCALE = r'scale-%dpc'
# regular expression patters for determining scale and user
REEXP_FOLDER_ANNOT = r'(.\S+)_scale-(\d+)pc'
REEXP_FOLDER_SCALE = r'\S*scale-(\d+)pc'
# default figure size for visualisations
FIGURE_SIZE = 18
# expected image extensions
IMAGE_EXT = ('.png', '.jpg', '.jpeg')
COLORS = 'grbm'


def update_path(path, max_depth=5):
    """ bobble up to find a particular path

    :param str path:
    :param int max_depth:
    :return str:

    >>> os.path.isdir(update_path('handlers'))
    True
    >>> os.path.isdir(update_path('no-handlers'))
    False
    """
    path_in = path
    if path.startswith('/'):
        return path
    for _ in range(max_depth):
        if os.path.exists(path):
            break
        path = os.path.join('..', path)

    path = os.path.abspath(path) if os.path.exists(path) else path_in
    return path


def assert_paths(args):
    """ check missing paths

    :param {} args: dictionary of arguments
    :return {}: dictionary of updated arguments

    >>> assert_paths({'path_': 'missing'})  # doctest: +NORMALIZE_WHITESPACE +ELLIPSIS
    Traceback (most recent call last):
        ...
    AssertionError: missing: (path_) "missing"
    >>> assert_paths({'abc': 123})
    {'abc': 123}
    """
    for k in (k for k in args if 'path' in k):
        args[k] = update_path(args[k])
        assert os.path.exists(args[k]), 'missing: (%s) "%s"' % (k, args[k])
    return args


def list_sub_folders(path_folder, name='*'):
    sub_dirs = sorted([p for p in glob.glob(os.path.join(path_folder, name))
                       if os.path.isdir(p)])
    return sub_dirs


def wrap_execute_parallel(wrap_func, iterate_vals,
                          nb_jobs=NB_THREADS, desc=''):
    """ wrapper for execution parallel of single thread as for...

    :param wrap_func: function which will be excited in the iterations
    :param [] iterate_vals: list or iterator which will ide in iterations
    :param int nb_jobs: number og jobs running in parallel
    :param str desc: description for the bar

    >>> list(wrap_execute_parallel(lambda pts: pts ** 2, range(5), nb_jobs=1))
    [0, 1, 4, 9, 16]
    >>> list(wrap_execute_parallel(sum, [[0, 1]] * 5, nb_jobs=2))
    [1, 1, 1, 1, 1]
    """
    iterate_vals = list(iterate_vals)

    tqdm_bar = tqdm.tqdm(total=len(iterate_vals), desc=desc)

    if nb_jobs > 1:
        logging.debug('perform sequential in %i threads', nb_jobs)
        pool = mproc.Pool(nb_jobs)

        for out in pool.imap_unordered(wrap_func, iterate_vals):
            yield out
            if tqdm_bar is not None:
                tqdm_bar.update()
        pool.close()
        pool.join()
    else:
        for out in map(wrap_func, iterate_vals):
            yield out
            if tqdm_bar is not None:
                tqdm_bar.update()


def create_folder(path_base, folder):
    path_folder = os.path.join(path_base, folder)
    if not os.path.isdir(path_folder):
        os.mkdir(path_folder)
    return path_folder


def parse_path_user_scale(path):
    """ from given path with annotation parse user name and scale

    :param str path: path to the user folder
    :return (str, int):

    >>> parse_path_user_scale('user-KO_scale-.5pc')
    ('', nan)
    >>> parse_path_user_scale('scale-10pc')
    ('', nan)
    >>> parse_path_user_scale('user-JB_scale-50pc')
    ('JB', 50)
    >>> parse_path_user_scale('sample/path/user-ck6_scale-25pc')
    ('ck6', 25)
    """
    path = os.path.basename(path)
    obj = re.match(REEXP_FOLDER_ANNOT, path)
    if obj is None:
        return '', np.nan
    user, scale = obj.groups()
    user = user.replace('user-', '')
    scale = int(scale)
    return user, scale


def parse_path_scale(path):
    """ from given path with annotation parse scale

    :param str path: path to the user folder
    :return int:

    >>> parse_path_scale('scale-.1pc')
    nan
    >>> parse_path_scale('user-JB_scale-50pc')
    50
    >>> parse_path_scale('scale-10pc')
    10
    """
    path = os.path.basename(path)
    obj = re.match(REEXP_FOLDER_SCALE, path)
    if obj is None:
        return np.nan
    scale = int(obj.groups()[0])
    return scale


def landmarks_consensus(list_landmarks):
    """ compute consensus as mean over all landmarks

    :param [DF] list_landmarks: list of DataFrames
    :return DF:

    >>> lnds1 = pd.DataFrame(np.zeros((5, 2)), columns=['X', 'Y'])
    >>> lnds2 = pd.DataFrame(np.ones((6, 2)), columns=['X', 'Y'])
    >>> landmarks_consensus([lnds1, lnds2])
         X    Y
    0  0.5  0.5
    1  0.5  0.5
    2  0.5  0.5
    3  0.5  0.5
    4  0.5  0.5
    5  1.0  1.0
    """
    lens = [len(lnd) for lnd in list_landmarks]
    df = list_landmarks[np.argmax(lens)]
    lens = sorted(set(lens), reverse=True)
    for l in lens:
        for ax in ['X', 'Y']:
            df[ax][:l] = np.mean([lnd[ax].values[:l]
                                  for lnd in list_landmarks
                                  if len(lnd) >= l], axis=0)
    return df


def collect_triple_dir(paths_landmarks, path_dataset, path_out, coll_dirs=None,
                       scales=None, with_user=False):
    """ collect all subdir up to level of scales with user annotations

    expected annotation structure is <tissue>/<user>_scale-<number>pc/<csv-file>
    expected dataset structure is <tissue>/scale-<number>pc/<image>

    :param [str] paths_landmarks: path to landmarks / annotations
    :param str path_dataset: path to the dataset with images
    :param str path_out: path for exporting statistic
    :param [{}] coll_dirs: list of already exiting collections
    :param [int] scales: list of allowed scales
    :param bool with_user: whether required iser info (as annotation)
    :return [{}]: list of already collections

    >>> coll_dirs, d = collect_triple_dir([update_path('annotations')],
    ...                                   update_path('dataset'), 'output')
    >>> len(coll_dirs) > 0
    True
    >>> 'annotations' in coll_dirs[0]['landmarks'].split(os.sep)
    True
    >>> 'dataset' in coll_dirs[0]['images'].split(os.sep)
    True
    >>> 'output' in coll_dirs[0]['output'].split(os.sep)
    True
    >>> d
    []
    """
    if coll_dirs is None:
        coll_dirs = []
    for path_lnds in paths_landmarks:
        set_name, scale_name = path_lnds.split(os.sep)[-2:]
        scale = parse_path_user_scale(scale_name)[1] \
            if with_user else parse_path_scale(scale_name)
        # if a scale was not recognised in the last folder name
        if np.isnan(scale):
            sub_dirs = list_sub_folders(path_lnds)
            coll_dirs, sub_dirs = collect_triple_dir(sub_dirs, path_dataset,
                                                     path_out, coll_dirs,
                                                     scales, with_user)
            continue
        # skip particular scale if it is not among chosen
        if scales is not None and scale not in scales:
            continue
        coll_dirs.append({
            'landmarks': path_lnds,
            'images': os.path.join(path_dataset, set_name,
                                   TEMPLATE_FOLDER_SCALE % scale),
            'output': os.path.join(path_out, set_name, scale_name)
        })
    return coll_dirs, []


def estimate_affine_transform(points_0, points_1):
    """ estimate Affine transformations and warp particular points sets
    to the other coordinate frame

    :param ndarray points_0: set of points
    :param ndarray points_1: set of points
    :return (ndarray, ndarray, ndarray): transform. matrix and warped point sets

    >>> pts0 = np.array([[4., 116.], [4., 4.], [26., 4.], [26., 116.]], dtype=int)
    >>> pts1 = np.array([[61., 56.], [61., -56.], [39., -56.], [39., 56.]])
    >>> matrix, pts0_w, pts1_w = estimate_affine_transform(pts0, pts1)
    >>> np.round(matrix, 2)
    array([[ -1.,   0.,  -0.],
           [  0.,   1.,  -0.],
           [ 65., -60.,   1.]])
    >>> pts0_w
    array([[ 61.,  56.],
           [ 61., -56.],
           [ 39., -56.],
           [ 39.,  56.]])
    >>> pts1_w
    array([[   4.,  116.],
           [   4.,    4.],
           [  26.,    4.],
           [  26.,  116.]])
    """
    # SEE: https://stackoverflow.com/questions/20546182
    nb = min(len(points_0), len(points_1))
    # Pad the data with ones, so that our transformation can do translations
    pad = lambda pts: np.hstack([pts, np.ones((pts.shape[0], 1))])
    unpad = lambda pts: pts[:, :-1]
    x = pad(points_0[:nb])
    y = pad(points_1[:nb])

    # Solve the least squares problem X * A = Y to find our transform. matrix A
    matrix, _, _, _ = np.linalg.lstsq(x, y, rcond=-1)

    transform = lambda pts: unpad(np.dot(pad(pts), matrix))
    points_0_warp = transform(points_0)

    transform_inv = lambda pts: unpad(np.dot(pad(pts), np.linalg.pinv(matrix)))
    points_1_warp = transform_inv(points_1)

    return matrix, points_0_warp, points_1_warp


def estimate_landmark_outliers(points_0, points_1, std_coef=5):
    """ estimated landmark outliers after affine alignment

    :param ndarray points_0: set ot points
    :param ndarray points_1: set ot points
    :param float std_coef:
    :return ([bool], [float]): vector or binary outliers and computed error

    >>> lnds0 = np.array([[4., 116.], [4., 4.], [26., 4.], [26., 116.],
    ...                   [18, 45], [0, 0], [-12, 8], [1, 1]])
    >>> lnds1 = np.array([[61., 56.], [61., -56.], [39., -56.], [39., 56.],
    ...                   [47., -15.], [65., -60.], [77., -52.], [0, 0]])
    >>> out, err = estimate_landmark_outliers(lnds0, lnds1, std_coef=3)
    >>> out.astype(int)
    array([0, 0, 0, 0, 0, 0, 0, 1])
    >>> np.round(err, 2)
    array([  1.02,  16.78,  10.29,   5.47,   6.88,  18.52,  20.94,  68.96])
    """
    nb = min(len(points_0), len(points_1))
    _, points_0w, _ = estimate_affine_transform(points_0[:nb], points_1[:nb])
    err = np.sqrt(np.sum((points_1[:nb] - points_0w) ** 2, axis=1))
    norm = np.std(err) * std_coef
    out = (err > norm)
    return out, err


def compute_landmarks_statistic(landmarks_ref, landmarks_in, use_affine=False,
                                im_size=None):
    """ compute statistic on errors between reference and sensed landmarks

    :param ndarray landmarks_ref:
    :param ndarray landmarks_in:
    :param bool use_affine:
    :param im_size:
    :return:

    >>> lnds0 = np.array([[4., 116.], [4., 4.], [26., 4.], [26., 116.],
    ...                   [18, 45], [0, 0], [-12, 8], [1, 1]])
    >>> lnds1 = np.array([[61., 56.], [61., -56.], [39., -56.], [39., 56.],
    ...                   [47., -15.], [65., -60.], [77., -52.], [0, 0]])
    >>> d_stat = compute_landmarks_statistic(lnds0, lnds1, use_affine=True)
    >>> [(k, d_stat[k]) for k in sorted(d_stat)]  # doctest: +NORMALIZE_WHITESPACE +ELLIPSIS
    [('TRE count', 8.0),
     ('TRE max', 68.9...),
     ('TRE mean', 18.6...),
     ('TRE median', 13.5...),
     ('TRE min', 1.0...),
     ('TRE std', 21.4...),
     ('image diagonal (estimated)', 85.7...),
     ('image size (estimated)', (65, 56)),
     ('rTRE max', 0.8...),
     ('rTRE mean', 0.2...),
     ('rTRE min', 0.01...),
     ('rTRE std', 0.25...)]
    >>> d_stat = compute_landmarks_statistic(lnds0, lnds1, im_size=(150, 175))
    >>> d_stat['TRE mean']  # doctest: +ELLIPSIS
    69.0189...
    """
    if isinstance(landmarks_ref, pd.DataFrame):
        landmarks_ref = landmarks_ref[['X', 'Y']].values
    if isinstance(landmarks_in, pd.DataFrame):
        landmarks_in = landmarks_in[['X', 'Y']].values

    if use_affine:
        _, err = estimate_landmark_outliers(landmarks_ref, landmarks_in)
    else:
        nb = min(len(landmarks_ref), len(landmarks_in))
        err = np.sqrt(np.sum((landmarks_ref[:nb] - landmarks_in[:nb]) ** 2, axis=1))
    df_err = pd.DataFrame(err)
    df_stat = df_err.describe().T[['count', 'mean', 'std', 'min', 'max']]
    df_stat.columns = ['TRE %s' % col for col in df_stat.columns]
    d_stat = dict(df_stat.iloc[0])
    d_stat['TRE median'] = np.median(err)

    if im_size is None:
        landmarks = np.concatenate([landmarks_ref, landmarks_in], axis=0)
        # assuming that the offset is symmetric on all sides
        im_size = (np.max(landmarks, axis=0) + np.min(landmarks, axis=0))
        logging.debug('estimated image size from landmarks: %s', repr(im_size))
        tp = 'estimated'
    else:
        tp = 'true'

    im_size = np.array(im_size[:2], dtype=int)
    im_diag = np.sqrt(np.sum(im_size ** 2))
    d_stat['image size (%s)' % tp] = tuple(im_size.tolist())
    d_stat['image diagonal (%s)' % tp] = np.sqrt(np.sum(im_size ** 2))

    for m in ['mean', 'std', 'min', 'max']:
        d_stat['rTRE %s' % m] = d_stat['TRE %s' % m] / im_diag

    return d_stat


def create_consensus_landmarks(path_annots, equal_size=True):
    """ create a consensus on set of landmarks and return normalised to 100%

    :param [str] path_annots: path to CSV landmarks
    :param bool equal_size: use only max number of common points, 56 & 65 -> 56
    :return {str: DF}:

    >>> folder = './me-KJ_25'
    >>> os.mkdir(folder)
    >>> create_consensus_landmarks([folder])
    ({}, {})
    >>> import shutil
    >>> shutil.rmtree(folder)
    """
    dict_list_lnds = {}
    # find all landmark for particular image
    for p_annot in path_annots:
        _, scale = parse_path_user_scale(p_annot)
        if np.isnan(scale):
            logging.warning('wrong set annotation scale, '
                            'required `<user>_scale-<number>pc` but got %s',
                            os.path.basename(p_annot))
            continue
        list_csv = glob.glob(os.path.join(p_annot, '*.csv'))
        for p_csv in list_csv:
            name = os.path.basename(p_csv)
            if name not in dict_list_lnds:
                dict_list_lnds[name] = []
            df_base = pd.read_csv(p_csv, index_col=0) / (scale / 100.)
            dict_list_lnds[name].append(df_base)

    dict_lnds, dict_lens = {}, {}
    # create consensus over particular landmarks
    for name in dict_list_lnds:
        dict_lens[name] = len(dict_list_lnds[name])
        # cases where the number od points is different
        df = landmarks_consensus(dict_list_lnds[name])
        dict_lnds[name] = df

    # take the minimal set or landmarks over whole set
    if equal_size and len(dict_lnds) > 0:
        nb_min = min([len(dict_lnds[n]) for n in dict_lnds])
        dict_lnds = {n: dict_lnds[n][:nb_min] for n in dict_lnds}

    return dict_lnds, dict_lens


def create_figure(im_size, max_fig_size=FIGURE_SIZE):
    norm_size = np.array(im_size) / float(np.max(im_size))
    # reverse dimensions and scale by fig size
    fig_size = norm_size[::-1] * max_fig_size
    fig, ax = plt.subplots(figsize=fig_size)
    return fig, ax


def format_figure(fig, ax, im_size, lnds):
    ax.set_xlim([min(0, np.min(lnds[1])), max(im_size[1], np.max(lnds[1]))])
    ax.set_ylim([max(im_size[0], np.max(lnds[0])), min(0, np.min(lnds[0]))])
    fig.tight_layout()
    return fig


def figure_image_landmarks(landmarks, image, max_fig_size=FIGURE_SIZE):
    """ create a figure with images and landmarks

    :param ndarray landmarks: landmark coordinates
    :param ndarray image: 2D image
    :param int max_fig_size:
    :return Figure:

    >>> import matplotlib
    >>> np.random.seed(0)
    >>> lnds = np.random.randint(-10, 25, (10, 2))
    >>> img = np.random.random((20, 30))
    >>> fig = figure_image_landmarks(lnds, img)
    >>> isinstance(fig, matplotlib.figure.Figure)
    True
    >>> df_lnds = pd.DataFrame(lnds, columns=['X', 'Y'])
    >>> fig = figure_image_landmarks(df_lnds, None)
    >>> isinstance(fig, matplotlib.figure.Figure)
    True
    """
    if isinstance(landmarks, pd.DataFrame):
        landmarks = landmarks[['X', 'Y']].values
    if image is None:
        image = np.zeros(np.max(landmarks, axis=0) + 25)

    fig, ax = create_figure(image.shape[:2], max_fig_size)

    ax.imshow(image)
    ax.plot(landmarks[:, 0], landmarks[:, 1], 'go')
    ax.plot(landmarks[:, 0], landmarks[:, 1], 'r.')

    for i, lnd in enumerate(landmarks):
        ax.text(lnd[0] + 5, lnd[1] + 5, str(i + 1), fontsize=11, color='black')

    fig = format_figure(fig, ax, image.shape[:2], landmarks)

    return fig


def figure_pair_images_landmarks(pair_landmarks, pair_images, names=None,
                                 max_fig_size=FIGURE_SIZE):
    """ create a figure with image pair and connect related landmarks by line

    :param (ndarray) pair_landmarks: set of landmark coordinates
    :param (ndarray) pair_images: set of 2D image
    :param [str] names: names
    :param int max_fig_size:
    :return Figure:

    >>> import matplotlib
    >>> np.random.seed(0)
    >>> lnds = np.random.randint(-10, 25, (10, 2))
    >>> img = np.random.random((20, 30))
    >>> fig = figure_pair_images_landmarks((lnds, lnds + 5), (img, img))
    >>> isinstance(fig, matplotlib.figure.Figure)
    True
    >>> df_lnds = pd.DataFrame(lnds, columns=['X', 'Y'])
    >>> fig = figure_pair_images_landmarks((df_lnds, df_lnds), (img, None))
    >>> isinstance(fig, matplotlib.figure.Figure)
    True
    """
    assert len(pair_landmarks) == len(pair_images), \
        'not equal counts for images (%i) and landmarks (%i)' \
        % (len(pair_landmarks), len(pair_images))
    pair_landmarks = list(pair_landmarks)
    pair_images = list(pair_images)
    for i, landmarks in enumerate(pair_landmarks):
        if isinstance(landmarks, pd.DataFrame):
            pair_landmarks[i] = landmarks[['X', 'Y']].values
    for i, image in enumerate(pair_images):
        if image is None:
            pair_images[i] = np.zeros(np.max(pair_landmarks[i], axis=0) + 25)

    im_size = np.max([img.shape[:2] for img in pair_images], axis=0)
    fig, ax = create_figure(im_size, max_fig_size)

    # draw semi transparent images
    for image in pair_images:
        ax.imshow(image, alpha=(1. / len(pair_images)))

    # draw lined between landmarks
    for i, lnds2 in enumerate(pair_landmarks[1:]):
        lnds1 = pair_landmarks[i]
        outliers, _ = estimate_landmark_outliers(lnds1, lnds2)
        for (x1, y1), (x2, y2), out in zip(lnds1, lnds2, outliers):
            ln = '-' if out else '-.'
            ax.plot([x1, x2], [y1, y2], ln, color=COLORS[i % len(COLORS)])

    if names is None:
        names = ['image %i' % i for i in range(len(pair_landmarks))]
    # draw all landmarks
    for i, landmarks in enumerate(pair_landmarks):
        ax.plot(landmarks[:, 0], landmarks[:, 1], 'o',
                color=COLORS[i % len(COLORS)], label=names[i])

    assert len(pair_landmarks) > 0, 'missing any landmarks'
    for i, lnd in enumerate(pair_landmarks[0]):
        ax.text(lnd[0] + 5, lnd[1] + 5, str(i + 1), fontsize=11, color='black')

    ax.legend()

    fig = format_figure(fig, ax, im_size, ([lnds[0] for lnds in pair_landmarks],
                                           [lnds[1] for lnds in pair_landmarks]))

    return fig


def load_image(img_path):
    """ loading very large images

    Note, for the loading we have to use matplotlib while ImageMagic nor other
     lib (opencv, skimage, Pillow) is able to load larger images then 64k or 32k.

    :param str img_path: path to the image
    :return ndarray: image

    >>> img = np.random.random((150, 200, 4))
    >>> n_img = 'sample-image.png'
    >>> plt.imsave(n_img, img)
    >>> load_image(n_img).shape
    (150, 200, 3)
    >>> os.remove(n_img)
    """
    assert os.path.isfile(img_path), 'missing image: %s' % img_path
    img = plt.imread(img_path)
    if img.ndim == 3 and img.shape[2] == 4:
        img = img[:, :, :3]
    return img


def get_file_ext(path_file):
    return os.path.splitext(os.path.basename(path_file))[-1]


def find_images(path_folder, name_file):
    """ find find images in particular flder with given file name

    :param str path_folder:
    :param str name_file:
    :return [str]:

    >>> path_dir = update_path(os.path.join('dataset', 'lung-lesion_3', 'scale-5pc'))
    >>> find_images(path_dir, '29-041-Izd2-w35-Cc10-5-les3')  # doctest: +ELLIPSIS
    ['...dataset/lung-lesion_3/scale-5pc/29-041-Izd2-w35-Cc10-5-les3.jpg']
    """
    assert os.path.isdir(path_folder), 'missing folder: %s' % path_folder
    paths_img = [p for p in glob.glob(os.path.join(path_folder, name_file + '.*'))
                 if get_file_ext(p) in IMAGE_EXT]
    return sorted(paths_img)


def find_image_full_size(path_dataset, name_set, name_image):
    """ find the smallest image of given tissue and stain and return images size

    :param str path_dataset: path to the image dataset
    :param str name_set: name of particular tissue
    :param str name_image: image name - stain
    :return (int, int):

    >>> find_image_full_size(update_path('dataset'), 'lung-lesion_3',
    ...                      '29-041-Izd2-w35-He-les3')
    (13220, 17840)
    >>> find_image_full_size(update_path('dataset'), 'lung-lesion_1', '29-...-He')
    """
    if path_dataset is None:
        return None
    path_set = os.path.join(path_dataset, name_set)
    if not os.path.isdir(path_set):
        return None
    paths_img = glob.glob(os.path.join(path_set, 'scale-*pc', name_image + '.*'))
    scales_paths_img = [(parse_path_scale(os.path.dirname(p)), p)
                        for p in paths_img if get_file_ext(p) in IMAGE_EXT]
    if not scales_paths_img:
        return None
    scale, path_img = sorted(scales_paths_img)[0]
    im_size = load_image(path_img).shape[:2]
    im_size_full = np.array(im_size) * (100. / scale)
    return tuple(im_size_full.astype(int))