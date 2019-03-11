import os
import json
import argparse
import torch
import data_loader.data_loaders as module_data
import model.loss as module_loss
import model.metric as module_metric
import model.model as module_arch
import utils.visualization as module_visualization
from trainer import Trainer
from utils import Logger
from utils import tps
from torch.utils.data import DataLoader
import torch.utils.data.dataloader


def get_instance(module, name, config, *args, **kwargs):
    return getattr(module, config[name]['type'])(*args, **config[name]['args'], **kwargs)


def coll(batch):
    b = torch.utils.data.dataloader.default_collate(batch)
    # Flatten to be 4D
    return [bi.reshape((-1,) + bi.shape[-3:]) if isinstance(bi, torch.Tensor) else bi for bi in b]


def main(config, resume):
    train_logger = Logger()

    # setup data_loader instances
    imwidth = config['dataset']['args']['imwidth']
    warper = get_instance(tps, 'warper', config, imwidth, imwidth)
    dataset = get_instance(module_data, 'dataset', config, pair_warper=warper)
    data_loader = DataLoader(dataset, batch_size=27, shuffle=True, drop_last=True, collate_fn=coll)
    val_dataset = get_instance(module_data, 'dataset', config, train=False, pair_warper=warper)
    valid_data_loader = DataLoader(val_dataset, batch_size=32, collate_fn=coll)

    # build model architecture
    model = get_instance(module_arch, 'arch', config)
    # print(model)

    # get function handles of loss and metrics
    loss = getattr(module_loss, config['loss'])
    metrics = [getattr(module_metric, met) for met in config['metrics']]
    visualizations = [getattr(module_visualization, vis) for vis in config['visualizations']]

    # build optimizer, learning rate scheduler. delete every lines containing lr_scheduler for disabling scheduler
    trainable_params = filter(lambda p: p.requires_grad, model.parameters())
    optimizer = get_instance(torch.optim, 'optimizer', config, trainable_params)
    lr_scheduler = get_instance(torch.optim.lr_scheduler, 'lr_scheduler', config, optimizer)

    trainer = Trainer(model, loss, metrics, optimizer,
                      resume=resume,
                      config=config,
                      data_loader=data_loader,
                      valid_data_loader=valid_data_loader,
                      lr_scheduler=lr_scheduler,
                      train_logger=train_logger,
                      visualizations=visualizations)

    trainer.train()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='PyTorch Template')
    parser.add_argument('-c', '--config', default=None, type=str,
                        help='config file path (default: None)')
    parser.add_argument('-r', '--resume', default=None, type=str,
                        help='path to latest checkpoint (default: None)')
    parser.add_argument('-d', '--device', default=None, type=str,
                        help='indices of GPUs to enable (default: all)')
    parser.add_argument('-f', '--folded_correlation', default=0, type=int,
                        help='whether to use folded correlation (reduces memory)')
    parser.add_argument('-p', '--profile', default=0, type=int,
                        help='whether to use print out profiling information')
    args = parser.parse_args()

    if args.config:
        # load config file
        config = json.load(open(args.config))
        path = os.path.join(config['trainer']['save_dir'], config['name'])
    elif args.resume:
        # load config file from checkpoint, in case new config file is not given.
        # Use '--config' and '--resume' arguments together to load trained model and train more with changed config.
        config = torch.load(args.resume)['config']
    else:
        raise AssertionError("Configuration file need to be specified. Add '-c config.json', for example.")
    config["folded_correlation"] = args.folded_correlation
    config["profile"] = args.profile

    if args.device:
        os.environ["CUDA_VISIBLE_DEVICES"] = args.device

    main(config, args.resume)
