# Copyright 2019 Lorna Authors. All Rights Reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================

import argparse
import os
import random

import torch.backends.cudnn as cudnn
import torch.utils.data
from torch.optim.rmsprop import RMSprop

from model.mlp import MLP_Discriminator
from model.mlp import MLP_Generate
from utils.datasets import load_datasets
from utils.visual import save_image

parser = argparse.ArgumentParser()
parser.add_argument('--dataroot', type=str, default='~/pytorch_datasets', help='path to dataset')
parser.add_argument('--batch_size', type=int, default=64, help='inputs batch size')
parser.add_argument('--img_size', type=int, default=32, help='the height / width of the inputs image to network')
parser.add_argument('--nc', type=int, default=3, help="image channels RGB.")
parser.add_argument('--nz', type=int, default=100, help='size of the latent z vector')
parser.add_argument('--n_epochs', type=int, default=200, help='number of epochs to train for')
parser.add_argument('--lr', type=float, default=0.00005, help='learning rate, default=0.00005')
parser.add_argument('--beta1', type=float, default=0.5, help='beta1 for adam. default=0.5')
parser.add_argument('--beta2', type=float, default=0.999, help='beta2 for adam. default=0.999')
parser.add_argument("--n_critic", type=int, default=5, help='number of training steps for discriminator per iter')
parser.add_argument("--clip_value", type=float, default=0.01, help='lower and upper clip value for disc. weights')
parser.add_argument('--cuda', action='store_true', help='enables cuda')
parser.add_argument('--ngpu', type=int, default=1, help='number of GPUs to use')
parser.add_argument('--netG', default='', help="path to netG (to continue training)")
parser.add_argument('--netD', default='', help="path to netD (to continue training)")
parser.add_argument('--out_images', default='./imgs', help='folder to output images')
parser.add_argument('--checkpoints_dir', default='./checkpoints', help='folder to output model checkpoints')
parser.add_argument('--manualSeed', type=int, help='manual seed')
parser.add_argument('--phase', type=str, default='eval', help='model mode. default=`train`')
parser.add_argument('--sample_size', type=int, default=1000, help='generate 1000 pic use classifier.')

opt = parser.parse_args()
print(opt)

try:
  os.makedirs(opt.out_images)
  os.makedirs("./unknown")
except OSError:
  pass

if opt.manualSeed is None:
  opt.manualSeed = random.randint(1, 10000)
random.seed(opt.manualSeed)
torch.manual_seed(opt.manualSeed)

cudnn.benchmark = True

if torch.cuda.is_available() and not opt.cuda:
  print("WARNING: You have a CUDA device, so you should probably run with --cuda")

device = torch.device("cuda:0" if opt.cuda else "cpu")

fixed_noise = torch.randn(opt.batch_size, opt.nz, device=device)


def main():
  """ train model
  """
  try:
    os.makedirs(opt.checkpoints_dir)
  except OSError:
    pass

  dataloader = load_datasets(opt)

  if torch.cuda.device_count() > 1:
    netG = torch.nn.DataParallel(MLP_Generate(opt))
  else:
    netG = MLP_Generate(opt)
  if opt.netG != '':
    netG.load_state_dict(torch.load(opt.netG, map_location=lambda storage, loc: storage))

  if torch.cuda.device_count() > 1:
    netD = torch.nn.DataParallel(MLP_Discriminator(opt))
  else:
    netD = MLP_Discriminator(opt)
  if opt.netD != '':
    netD.load_state_dict(torch.load(opt.netD, map_location=lambda storage, loc: storage))

  # set train mode
  netG.train()
  netG = netG.to(device)
  netD.train()
  netD = netD.to(device)
  print(netG)
  print(netD)

  ################################################
  #            Use RMSprop optimizer
  ################################################
  optimizerD = RMSprop(netD.parameters(), lr=opt.lr)
  optimizerG = RMSprop(netG.parameters(), lr=opt.lr)

  ################################################
  #               print args
  ################################################
  print("########################################")
  print(f"train dataset path: {opt.dataroot}")
  print(f"batch size: {opt.batch_size}")
  print(f"image size: {opt.image_size}")
  print(f"Epochs: {opt.n_epochs}")
  print(f"Noise size: {opt.nz}")
  print("########################################")
  print("Starting trainning!")
  for epoch in range(opt.n_epochs):
    for i, data in enumerate(dataloader):
      # get data
      real_imgs = data[0].to(device)
      batch_size = real_imgs.size(0)

      # Sample noise as generator input
      z = torch.randn(batch_size, opt.nz, device=device)

      ##############################################
      # (1) Update D network: maximize log(D(x)) + log(1 - D(G(z)))
      ##############################################

      optimizerD.zero_grad()

      # Generate a batch of images
      fake_imgs = netG(z).detach()

      # Adversarial loss
      real_output = netD(real_imgs)
      fake_output = netD(fake_imgs)
      loss_D = -torch.mean(real_output) + torch.mean(fake_output)

      loss_D.backward()
      optimizerD.step()

      # Clip weights of discriminator
      for p in netD.parameters():
        p.data.clamp_(-opt.clip_value, opt.clip_value)

      ##############################################
      # (2) Update G network: maximize log(D(G(z)))
      ##############################################
      if i % opt.n_critic == 0:
        optimizerG.zero_grad()

        # Generate a batch of images
        fake_imgs = netG(z)

        # Adversarial loss
        loss_G = -torch.mean(netD(fake_imgs))

        loss_G.backward()
        optimizerG.step()

        print(f"Epoch->[{epoch + 1:03d}/{opt.n_epochs:03d}] "
              f"Progress->{i / len(dataloader) * 100:4.2f}% "
              f"Loss_D: {loss_D.item():.4f} "
              f"Loss_G: {loss_G.item():.4f} ", end="\r")

      if i % 100 == 0:
        save_image(real_imgs, f"{opt.out_images}/real_samples.png")
        with torch.no_grad():
          fake = netG(fixed_noise).detach().cpu()
        save_image(fake.detach().cpu(), f"{opt.out_images}/fake_samples_epoch_{epoch + 1:03d}.png")

    # do checkpointing
    torch.save(netG.state_dict(), f"{opt.checkpoints_dir}/netG_epoch_{epoch + 1:03d}.pth")
    torch.save(netD.state_dict(), f"{opt.checkpoints_dir}/netD_epoch_{epoch + 1:03d}.pth")


if __name__ == '__main__':
  main()