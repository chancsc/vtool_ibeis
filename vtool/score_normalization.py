# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function
import utool
import numpy as np
import utool as ut
import six  # NOQA
print, print_, printDBG, rrr, profile = utool.inject(__name__, '[scorenorm]', DEBUG=False)


def learn_score_normalization(tp_support, tn_support, gridsize=1024,
                              adjust=8, return_all=False, monotonize=True,
                              clip_factor=(ut.PHI + 1)):
    r"""
    Takes collected data and applys parzen window density estimation and bayes rule.

    Args:
        tp_support (ndarray):
        tn_support (ndarray):
        gridsize       (int): default 512
        adjust         (int): default 8
        return_all     (bool): default False
        monotonize     (bool): default True
        clip_factor    (float): default phi ** 2

    Returns:
        tuple: (score_domain, p_tp_given_score, p_tn_given_score, p_score_given_tp, p_score_given_tn, p_score, clip_score)

    Example:
        >>> # ENABLE_DOCTEST
        >>> from ibeis.model.hots.score_normalization import *  # NOQA
        >>> tp_support = np.linspace(100, 10000, 512)
        >>> tn_support = np.linspace(0, 120, 512)
        >>> (score_domain, p_tp_given_score, clip_score) = learn_score_normalization(tp_support, tn_support)
        >>> result = int(p_tp_given_score.sum())
        >>> print(result)
        92
    """
    # Estimate true positive density
    score_tp_pdf = ut.estimate_pdf(tp_support, gridsize=gridsize, adjust=adjust)
    score_tn_pdf = ut.estimate_pdf(tn_support, gridsize=gridsize, adjust=adjust)
    # Find good maximum score (for domain not learning)
    #clip_score = 2000
    clip_score = find_score_maxclip(tp_support, tn_support, clip_factor)
    score_domain = np.linspace(0, clip_score, 1024)
    # Evaluate true negative density
    p_score_given_tp = score_tp_pdf.evaluate(score_domain)
    p_score_given_tn = score_tn_pdf.evaluate(score_domain)
    # Average to get probablity of any score
    p_score = (np.array(p_score_given_tp) + np.array(p_score_given_tn)) / 2.0
    # Apply bayes
    p_tp = .5
    p_tp_given_score = ut.bayes_rule(p_score_given_tp, p_tp, p_score)
    import vtool as vt
    if monotonize:
        p_tp_given_score = vt.ensure_monotone_strictly_increasing(
            p_tp_given_score, zerohack=True, onehack=True)
    if return_all:
        p_tn_given_score = 1 - p_tp_given_score
        return (score_domain, p_tp_given_score, p_tn_given_score,
                p_score_given_tp, p_score_given_tn, p_score, clip_score)
    else:
        return (score_domain, p_tp_given_score, clip_score)


def find_score_maxclip(tp_support, tn_support, clip_factor=ut.PHI + 1):
    """
    returns score to clip true positives past.

    Args:
        tp_support (ndarray):
        tn_support (ndarray):

    Returns:
        float: clip_score

    Example:
        >>> # ENABLE_DOCTEST
        >>> from ibeis.model.hots.score_normalization import *  # NOQA
        >>> tp_support = np.array([100, 200, 50000])
        >>> tn_support = np.array([10, 30, 110])
        >>> clip_score = find_score_maxclip(tp_support, tn_support)
        >>> result = str(clip_score)
        >>> print(result)
        287.983738762
    """
    max_true_positive_score = tp_support.max()
    max_true_negative_score = tn_support.max()
    if clip_factor is None:
        clip_score = max_true_positive_score
    else:
        overshoot_factor = max_true_positive_score / max_true_negative_score
        if overshoot_factor > clip_factor:
            clip_score = max_true_negative_score * clip_factor
        else:
            clip_score = max_true_positive_score
    return clip_score


def normalize_scores(score_domain, p_tp_given_score, scores):
    """
    Adjusts a raw scores to a probabilities based on a learned normalizer

    Args:
        score_domain (ndarray): input score domain
        p_tp_given_score (ndarray): learned probability mapping
        scores (ndarray): raw scores

    Returns:
        ndarray: probabilities

    CommandLine:
        python -m vtool.score_normalization --test-normalize_scores

    Example:
        >>> # ENABLE_DOCTEST
        >>> from vtool.score_normalization import *  # NOQA
        >>> score_domain = np.linspace(0, 10, 10)
        >>> p_tp_given_score = (score_domain ** 2) / (score_domain.max() ** 2)
        >>> scores = np.array([-1, 0.0, 0.01, 2.3, 8.0, 9.99, 10.0, 10.1, 11.1])
        >>> prob = normalize_scores(score_domain, p_tp_given_score, scores)
        >>> result = ut.numpy_str(prob, precision=2)
        >>> print(result)
        np.array([ 0.  ,  0.  ,  0.  ,  0.05,  0.6 ,  0.79,  1.  ,  1.  ,  1.  ], dtype=np.float64)
    """
    prob = np.zeros(len(scores))
    #prob = np.full(len(scores), np.nan)
    is_nan  = np.isnan(scores)
    is_low  = scores < score_domain[0]
    is_high = scores > score_domain[-1]
    is_ok = np.logical_not(np.logical_or.reduce((is_nan, is_low, is_high)))
    # interpolate scores in the learned domain
    # we are garuenteed to have nonzero elements here
    flags = score_domain <= scores[is_ok][:, None]
    left_indicies = np.array([np.nonzero(row)[0][-1] for row in flags])
    # TODO: interpolatio (see vt.histogram)
    # currently just taking the min
    prob[is_ok] = p_tp_given_score[left_indicies]
    # fill in other values
    assert not np.any(is_nan), 'cannot normalize nan values'
    #if any(is_nan):
    #    # handle nans
    #    raise AssertionError('user normalize score list')
    #    prob[np.isnan(score_domain)] = -1.0
    # clip low scores at 0
    prob[is_low] = 0
    # clip high scores by between max probability and one
    prob[is_high] = (p_tp_given_score[-1] + 1.0) / 2.0
    return prob


# DEBUGGING FUNCTIONS


def test_score_normalization(tp_support, tn_support):
    """
    Shows how score normalization works with gaussian noise

    CommandLine:
        python -m vtool.score_normalization --test-test_score_normalization --show

    Example:
        >>> # ENABLE_DOCTEST
        >>> from vtool.score_normalization import *  # NOQA
        >>> randstate = np.random.RandomState(seed=0)
        >>> # Get a training sample
        >>> tp_support = randstate.normal(loc=6.5, size=(256,))
        >>> tn_support = randstate.normal(loc=3.5, size=(256,))
        >>> test_score_normalization(tp_support, tn_support)
        >>> ut.show_if_requested()

    """
    import plottool as pt  # NOQA

    # Print raw score statistics
    ut.print_stats(tp_support, lbl='tp_support')
    ut.print_stats(tn_support, lbl='tn_support')

    # Test (potentially multiple) normalizing configurations
    normkw_list = ut.util_dict.all_dict_combinations(
        {
            'monotonize': [True],  # [True, False],
            #'adjust': [1, 4, 8],
            'adjust': [1],
            #'adjust': [8],
        }
    )

    if len(normkw_list) > 32:
        raise AssertionError('Too many plots to test!')

    fnum = pt.next_fnum()
    #plot_support(tn_support, tp_support, fnum=fnum)

    for normkw in normkw_list:
        # Learn the appropriate normalization
        #normkw = {}  # dict(gridsize=1024, adjust=8, clip_factor=ut.PHI + 1, return_all=True)
        (score_domain, p_tp_given_score, p_tn_given_score, p_score_given_tp, p_score_given_tn,
         p_score, clip_score) = learn_score_normalization(tp_support, tn_support, return_all=True, **normkw)

        assert clip_score > tn_support.max()

        inspect_pdfs(tn_support, tp_support, score_domain,
                     p_tp_given_score, p_tn_given_score, p_score_given_tp,
                     p_score_given_tn, p_score,
                     with_scores=True, with_roc=True, with_precision_recall=False)

        pt.adjust_subplots(hspace=.3, bottom=.05, left=.05)

        pt.set_figtitle('ScoreNorm test' + ut.dict_str(normkw, newlines=False))

        #confusions = get_confusion_metrics()
    locals_ = locals()
    return locals_


def inspect_pdfs(tn_support, tp_support, score_domain, p_tp_given_score,
                 p_tn_given_score, p_score_given_tp, p_score_given_tn, p_score,
                 with_scores=False, with_roc=False, with_precision_recall=False):
    import plottool as pt  # NOQA

    fnum = pt.next_fnum()
    nSubplots = 2 + with_scores + with_roc + with_precision_recall
    if True:
        nRows, nCols = pt.get_square_row_cols(nSubplots)
    else:
        nRows = nSubplots
        nCols = 1
    _pnumiter = pt.make_pnum_nextgen(nRows=nRows, nCols=nCols, nSubplots=nSubplots)

    #pt.figure(fnum=fnum, pnum=pnum_(0))

    if with_scores:
        #plot_support(tn_support, tp_support, fnum=fnum, pnum=_pnumiter(), markersizes=[5, 4], score_markers=['x', '+'])
        #plot_support(tn_support, tp_support, fnum=fnum, pnum=_pnumiter(), markersizes=[8, 8], score_markers=['1', '2'])
        #plot_support(tn_support, tp_support, fnum=fnum, pnum=_pnumiter(), markersizes=[8, 8], score_markers=['^', 'v'])
        plot_support(tn_support, tp_support, fnum=fnum, pnum=_pnumiter(), markersizes=[5, 5], score_markers=['^', 'v'])

    plot_prebayes_pdf(score_domain, p_score_given_tn, p_score_given_tp, p_score,
                      cfgstr='', fnum=fnum, pnum=_pnumiter())

    plot_postbayes_pdf(score_domain, p_tn_given_score, p_tp_given_score,
                       cfgstr='', fnum=fnum, pnum=_pnumiter())

    import vtool as vt

    scores = np.hstack([tn_support, tp_support])
    labels = np.array([False] * len(tn_support) + [True] * len(tp_support))
    probs = normalize_scores(score_domain, p_tp_given_score, scores)

    #import sklearn.metrics
    #sklearn.metrics.classification_report(labels, probs)
    confusions = vt.get_confusion_metrics(probs, labels)
    if with_roc:
        confusions.draw_roc_curve(fnum=fnum, pnum=_pnumiter())

    if with_precision_recall:
        confusions.draw_precision_recall_curve(fnum=fnum, pnum=_pnumiter())
    #ut.embed()


def plot_support(tn_support, tp_support, fnum=None, pnum=(1, 1, 1), figtitle='sorted scores', **kwargs):
    r"""
    Args:
        tn_support (ndarray):
        tp_support (ndarray):
        fnum (int):  figure number
        pnum (tuple):  plot number

    CommandLine:
        python -m ibeis.model.hots.score_normalization --test-plot_support

    Example:
        >>> # DISABLE_DOCTEST
        >>> from ibeis.model.hots.score_normalization import *  # NOQA
        >>> tn_support = '?'
        >>> tp_support = '?'
        >>> fnum = None
        >>> pnum = (1, 1, 1)
        >>> result = plot_support(tn_support, tp_support, fnum, pnum)
        >>> print(result)
    """
    import plottool as pt  # NOQA
    if fnum is None:
        fnum = pt.next_fnum()
    true_color = pt.TRUE_BLUE  # pt.TRUE_GREEN
    false_color = pt.FALSE_RED
    pt.plots.plot_sorted_scores(
        (tn_support, tp_support),
        ('trueneg scores', 'truepos scores'),
        score_colors=(false_color, true_color),
        #logscale=True,
        logscale=False,
        figtitle=figtitle,
        fnum=fnum,
        pnum=pnum,
        **kwargs)


def plot_prebayes_pdf(score_domain, p_score_given_tn, p_score_given_tp, p_score,
                      cfgstr='', fnum=None, pnum=(1, 1, 1)):
    import plottool as pt  # NOQA
    if fnum is None:
        fnum = pt.next_fnum()
    true_color = pt.TRUE_BLUE  # pt.TRUE_GREEN
    false_color = pt.FALSE_RED
    #unknown_color = pt.UNKNOWN_PURP
    unknown_color = pt.PURPLE2
    #unknown_color = pt.GRAY

    pt.plots.plot_probabilities(
        (p_score_given_tn,  p_score_given_tp, p_score),
        ('p(score | tn)', 'p(score | tp)', 'p(score)'),
        prob_colors=(false_color, true_color, unknown_color),
        figtitle='pre_bayes pdf score',
        xdata=score_domain,
        fnum=fnum,
        pnum=pnum)


def plot_postbayes_pdf(score_domain, p_tn_given_score, p_tp_given_score,
                       cfgstr='', fnum=None, pnum=(1, 1, 1)):
    import plottool as pt  # NOQA
    if fnum is None:
        fnum = pt.next_fnum()
    true_color = pt.TRUE_BLUE  # pt.TRUE_GREEN
    false_color = pt.FALSE_RED

    pt.plots.plot_probabilities(
        (p_tn_given_score, p_tp_given_score),
        ('p(tn | score)', 'p(tp | score)'),
        prob_colors=(false_color, true_color,),
        figtitle='post_bayes pdf score ' + cfgstr,
        xdata=score_domain, fnum=fnum, pnum=pnum)


if __name__ == '__main__':
    """
    CommandLine:
        python -m vtool.score_normalization
        python -m vtool.score_normalization --allexamples
        python -m vtool.score_normalization --allexamples --noface --nosrc
    """
    import multiprocessing
    multiprocessing.freeze_support()  # for win32
    import utool as ut  # NOQA
    ut.doctest_funcs()
