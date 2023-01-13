# 🦆 Uberduck Text-to-speech ![](https://img.shields.io/github/forks/uberduck-ai/uberduck-ml-dev) ![](https://img.shields.io/github/stars/uberduck-ai/uberduck-ml-dev) ![](https://img.shields.io/github/issues/uberduck-ai/uberduck-ml-dev)

[**Uberduck**](https://uberduck.ai/) is a tool for fun and creativity with voice cloning with neural text-to-speech. This repository will get you creating your own speech synthesis model. Please see our [**training**](https://colab.research.google.com/drive/1jF-Otw2_ssEcus4ISaIZu3QDmtifUvyY) and [**synthesis**](https://colab.research.google.com/drive/1wXWuhnw2pdfFy1L-pUzHfopW10W2GiJS) notebooks, and the [**Wiki**](https://github.com/uberduck-ai/uberduck-ml-dev/wiki).

<h1>Table of Contents<span class="tocSkip"></span></h1>
<div class="toc">
   <ul class="toc-item">
         <ul class="toc-item">
            <li><span><a href="#Overview" data-toc-modified-id="Overview-1.0"><span class="toc-item-num">1.0&nbsp;&nbsp;</span>Overview</a></span></li>
            <li><span><a href="#Installation" data-toc-modified-id="Installation-1.1"><span class="toc-item-num">1.1&nbsp;&nbsp;</span>Installation</a></span></li>
            <li><span><a href="#Usage" data-toc-modified-id="Usage-1.2"><span class="toc-item-num">1.2&nbsp;&nbsp;</span>Usage</a></span></li>
            <li>
               <span><a href="#Development" data-toc-modified-id="Development-1.3"><span class="toc-item-num">1.3&nbsp;&nbsp;</span>Development</a></span>
               <ul class="toc-item">
                  <li><span><a href="#🚩-Testing" data-toc-modified-id="🚩-Testing-1.2.0"><span class="toc-item-num">1.2.0&nbsp;&nbsp;</span>🚩 Testing</a></span></li>
               </ul>
               <ul class="toc-item">
                  <li><span><a href="#🔧-Troubleshooting-Tips" data-toc-modified-id="🔧-Troubleshooting-Tips-1.2.1"><span class="toc-item-num">1.2.1&nbsp;&nbsp;</span>🔧 Troubleshooting Tips</a></span></li>
               </ul>
            </li>
         </ul>
   </ul>
</div>

## Overview

This repository is based on the NVIDIA Mellotron.  The state of the various latent space features are.

\ Multispeaker training (functioning, beneficial)
\ Torchmoji conditioning (functioning, 
\ Mean speaker encoding (functioning)
\ Pitch conditioning (non functioning)
\ SRMR and MOSNet conditioning (non functioning)

It also includes teacher forcing type methods for prosody matching, and should compile for torchscript inference.

Entrypoint scripts for running training jobs are executed via a command like
`python -m uberduck_ml_dev.exec.train_tacotron2 --your-args here`

## Installation

```
conda create -n 'uberduck-ml-dev' python=3.8
source activate uberduck-ml-dev
pip install git+https://github.com/uberduck-ai/uberduck-ml-dev.git
```

## Usage

### Training

1. Download torchmoji models if training with Torchmoji GST.

   ```bash
   wget "https://github.com/johnpaulbin/torchMoji/releases/download/files/pytorch_model.bin" -O pytorch_model.bin
   wget "https://raw.githubusercontent.com/johnpaulbin/torchMoji/master/model/vocabulary.json" -O vocabulary.json
   ```
2. Create your training config. Use the training configs in the `configs` directory as a starting point, e.g. [this one](https://github.com/uberduck-ai/uberduck-ml-dev/blob/master/configs/tacotron2_config.json).
3. Start training. Example invocation for Tacotron2 training:
   ```bash
   python -m uberduck_ml_dev.exec.train_tacotron2 --config tacotron2_config.json
   ```

## Development


```bash
pip install pre-commit black # install the required development dependencies in a virtual environment
git clone git@github.com:uberduck-ai/uberduck-ml-dev.git # clone the repository:
pre-commit install # Install required Git hooks:
python setup.py develop # Install the library
```

### 🚩 Testing

In an environment with uberduck-ml-dev installed, run 

```bash
python -m pytest
```
