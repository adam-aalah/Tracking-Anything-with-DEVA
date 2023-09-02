import os
from os import path
from argparse import ArgumentParser

import torch
import numpy as np

from deva.inference.inference_core import DEVAInferenceCore
from deva.inference.result_utils import ResultSaver
from deva.inference.eval_args import add_common_eval_args, get_model_and_config
from deva.inference.demo_utils import flush_buffer
from deva.ext.ext_eval_args import add_ext_eval_args, add_auto_default_args
from deva.ext.automatic_sam import get_sam_model
from deva.ext.automatic_processor import process_frame_automatic as process_frame

from tqdm import tqdm
import json

if __name__ == '__main__':
    torch.autograd.set_grad_enabled(False)

    # for id2rgb
    np.random.seed(42)
    """
    Arguments loading
    """
    parser = ArgumentParser()

    add_common_eval_args(parser)
    add_ext_eval_args(parser)
    add_auto_default_args(parser)
    deva_model, cfg, args = get_model_and_config(parser)
    sam_model = get_sam_model(cfg, 'cuda')
    """
    Temporal setting
    """
    cfg['temporal_setting'] = args.temporal_setting.lower()
    assert cfg['temporal_setting'] in ['semionline', 'online']

    # get data
    frames = sorted(os.listdir(args.img_path))
    out_path = args.output

    # Start eval
    vid_length = len(frames)
    # no need to count usage for LT if the video is not that long anyway
    cfg['enable_long_term_count_usage'] = (
        cfg['enable_long_term']
        and (vid_length / (cfg['max_mid_term_frames'] - cfg['min_mid_term_frames']) *
             cfg['num_prototypes']) >= cfg['max_long_term_elements'])

    print('Configuration:', cfg)

    deva = DEVAInferenceCore(deva_model, config=cfg)
    deva.next_voting_frame = args.num_voting_frames - 1
    deva.enabled_long_id()
    result_saver = ResultSaver(out_path, None, dataset='demo', object_manager=deva.object_manager)

    with torch.cuda.amp.autocast(enabled=args.amp):
        for ti, frame in enumerate(tqdm(frames)):
            frame_path = path.join(args.img_path, frame)
            process_frame(deva, sam_model, frame_path, result_saver, ti)
        flush_buffer(deva, result_saver)

    # save this as a video-level json
    with open(path.join(out_path, 'pred.json'), 'w') as f:
        json.dump(result_saver.video_json, f, indent=4)  # prettier json