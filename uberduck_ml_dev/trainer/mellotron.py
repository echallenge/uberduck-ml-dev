# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/trainer.mellotron.ipynb (unless otherwise specified).

__all__ = ['MellotronTrainer']

# Cell
import os
from pathlib import Path
from pprint import pprint

import torch
from torch.cuda.amp import autocast, GradScaler
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.utils.tensorboard import SummaryWriter
import time
from torch.utils.data import DataLoader

from ..models.common import MelSTFT
from ..utils.plot import (
    plot_attention,
    plot_gate_outputs,
    plot_spectrogram,
)
from ..text.util import text_to_sequence, random_utterance
from .tacotron2 import Tacotron2Trainer, Tacotron2Loss
from ..models.mellotron import Mellotron
from ..data_loader import TextMelDataset, TextMelCollate


class MellotronTrainer(Tacotron2Trainer):
    REQUIRED_HPARAMS = [
        "audiopaths_and_text",
        "checkpoint_path",
        "epochs",
        "mel_fmax",
        "mel_fmin",
        "n_mel_channels",
        "text_cleaners",
        "pos_weight",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.n_frames_per_step_current = self.n_frames_per_step_initial
        self.reduction_window_idx = 0

    def adjust_frames_per_step(
        self,
        model: Mellotron,
        train_loader: DataLoader,
        sampler,
        collate_fn: TextMelCollate,
    ):
        """If necessary, adjust model and loader's n_frames_per_step."""
        if not self.reduction_window_schedule:
            return train_loader, sampler, collate_fn
        settings = self.reduction_window_schedule[self.reduction_window_idx]
        if settings["until_step"] is None:
            return train_loader, sampler, collate_fn
        if self.global_step < settings["until_step"]:
            return train_loader, sampler, collate_fn
        old_fps = settings["n_frames_per_step"]
        while settings["until_step"] and self.global_step >= settings["until_step"]:
            self.reduction_window_idx += 1
            settings = self.reduction_window_schedule[self.reduction_window_idx]
        fps = settings["n_frames_per_step"]
        bs = settings["batch_size"]
        print(f"Adjusting frames per step from {old_fps} to {fps}")
        self.batch_size = bs
        model.set_current_frames_per_step(fps)
        self.n_frames_per_step_current = fps
        _, _, train_loader, sampler, collate_fn = self.initialize_loader()
        return train_loader, sampler, collate_fn

    def validate(self, **kwargs):
        model = kwargs["model"]
        val_set = kwargs["val_set"]
        collate_fn = kwargs["collate_fn"]
        criterion = kwargs["criterion"]
        sampler = DistributedSampler(val_set) if self.distributed_run else None
        (
            total_loss,
            total_mel_loss,
            total_gate_loss,
            total_mel_loss_val,
            total_gate_loss_val,
        ) = (0, 0, 0, 0, 0)
        total_steps = 0
        model.eval()
        speakers_val = []
        total_mel_loss_val = []
        total_gate_loss_val = []
        with torch.no_grad():
            val_loader = DataLoader(
                val_set,
                sampler=sampler,
                shuffle=False,
                batch_size=self.batch_size,
                collate_fn=collate_fn,
            )
            for batch in val_loader:
                total_steps += 1
                if self.distributed_run:
                    X, y = model.module.parse_batch(batch)
                    speakers_val.append(X[5])
                else:
                    X, y = model.parse_batch(batch)
                    speakers_val.append(X[5])
                y_pred = model(X)
                mel_loss, gate_loss, mel_loss_batch, gate_loss_batch = criterion(
                    y_pred, y
                )
                if self.distributed_run:
                    reduced_mel_loss = reduce_tensor(mel_loss, self.world_size).item()
                    reduced_gate_loss = reduce_tensor(gate_loss, self.world_size).item()
                    reduced_val_loss = reduced_mel_loss + reduced_gate_loss
                else:
                    reduced_mel_loss = mel_loss.item()
                    reduced_gate_loss = gate_loss.item()
                    reduced_mel_loss_val = mel_loss_batch.detach()
                    reduced_gate_loss_val = gate_loss_batch.detach()

                total_mel_loss_val.append(reduced_mel_loss_val)
                total_gate_loss_val.append(reduced_gate_loss_val)
                reduced_val_loss = reduced_mel_loss + reduced_gate_loss
                total_mel_loss += reduced_mel_loss
                total_gate_loss += reduced_gate_loss
                total_loss += reduced_val_loss

            mean_mel_loss = total_mel_loss / total_steps
            mean_gate_loss = total_gate_loss / total_steps
            mean_loss = total_loss / total_steps
            total_mel_loss_val = torch.hstack(total_mel_loss_val)
            total_gate_loss_val = torch.hstack(total_gate_loss_val)
            speakers_val = torch.hstack(speakers_val)
            self.log_validation(
                X,
                y_pred,
                y,
                mean_loss,
                mean_mel_loss,
                mean_gate_loss,
                total_mel_loss_val,
                total_gate_loss_val,
                speakers_val,
            )
        model.train()

    def sample_inference(self, model):
        if self.rank is not None and self.rank != 0:
            return
        # Generate an audio sample
        with torch.no_grad():
            utterance = torch.LongTensor(
                text_to_sequence(random_utterance(), self.text_cleaners, self.p_arpabet)
            )[None].cuda()
            speaker_id = (
                choice(self.sample_inference_speaker_ids)
                if self.sample_inference_speaker_ids
                else randint(0, self.n_speakers - 1)
            )
            input_ = [utterance, 0, torch.LongTensor([speaker_id]).cuda()]
            if self.include_f0:
                input_.append(torch.zeros([1, 1, 200], device=self.device))
                # 200 can be changed
            model.eval()
            _, mel, gate, attn = model.inference(input_)
            model.train()
            try:
                audio = self.sample(mel[0])
                self.log("SampleInference", self.global_step, audio=audio)
            except Exception as e:
                print(f"Exception raised while doing sample inference: {e}")
                print("Mel shape: ", mel[0].shape)
            self.log(
                "Attention/sample_inference",
                self.global_step,
                image=save_figure_to_numpy(
                    plot_attention(attn[0].data.cpu().transpose(0, 1))
                ),
            )
            self.log(
                "MelPredicted/sample_inference",
                self.global_step,
                image=save_figure_to_numpy(plot_spectrogram(mel[0].data.cpu())),
            )
            self.log(
                "Gate/sample_inference",
                self.global_step,
                image=save_figure_to_numpy(
                    plot_gate_outputs(gate_outputs=gate[0].data.cpu())
                ),
            )

    @property
    def training_dataset_args(self):
        return [
            self.training_audiopaths_and_text,
            self.text_cleaners,
            self.p_arpabet,
            # audio params
            self.n_mel_channels,
            self.sampling_rate,
            self.mel_fmin,
            self.mel_fmax,
            self.filter_length,
            self.hop_length,
            self.win_length,
            self.max_wav_value,
            self.include_f0,
            self.pos_weight,
        ]

    #     def warm_start(self, model, optimizer, start_epoch=0):

    #         print("Starting warm_start", time.perf_counter())
    #         checkpoint = self.load_checkpoint()
    #         # TODO(zach): Once we are no longer using checkpoints of the old format, remove the conditional and use checkpoint["model"] only.
    #         model_state_dict = (
    #             checkpoint["model"] if "model" in checkpoint else checkpoint["state_dict"]
    #         )
    #         model.from_pretrained(
    #             model_dict=model_state_dict,
    #             device=self.device,
    #             ignore_layers=self.ignore_layers,
    #         )
    #         if "optimizer" in checkpoint and len(self.ignore_layers) == 0:
    #             optimizer.load_state_dict(checkpoint["optimizer"])
    #         if "iteration" in checkpoint:
    #             start_epoch = checkpoint["iteration"]
    #         if "learning_rate" in checkpoint:
    #             optimizer.param_groups[0]["lr"] = checkpoint["learning_rate"]
    #             self.learning_rate = checkpoint["learning_rate"]
    #         if "global_step" in checkpoint:
    #             self.global_step = checkpoint["global_step"]
    #             print(f"Adjusted global step to {self.global_step}")
    #         print("Ending warm_start", time.perf_counter())
    #         return model, optimizer, start_epoch

    def train(self):
        print("start train", time.perf_counter())
        train_set, val_set, train_loader, sampler, collate_fn = self.initialize_loader()
        criterion = Tacotron2Loss(
            pos_weight=self.pos_weight
        )  # keep higher than 5 to make clips not stretch on

        model = Mellotron(self.hparams)
        # move to TTSTrainer class
        if self.device == "cuda":
            model = model.cuda()
        if self.distributed_run:
            model = DDP(model, device_ids=[self.rank])
        optimizer = torch.optim.Adam(
            model.parameters(),
            lr=self.learning_rate,
            weight_decay=self.weight_decay,
        )
        start_epoch = 0

        if self.warm_start_name:
            model, optimizer, start_epoch = self.warm_start(model, optimizer)

        if self.fp16_run:
            scaler = GradScaler()

        # main training loop
        for epoch in range(start_epoch, self.epochs):
            train_loader, sampler, collate_fn = self.adjust_frames_per_step(
                model, train_loader, sampler, collate_fn
            )
            if self.distributed_run:
                sampler.set_epoch(epoch)
            for batch in train_loader:
                start_time = time.perf_counter()
                self.global_step += 1
                model.zero_grad()
                if self.distributed_run:
                    X, y = model.module.parse_batch(batch)
                else:
                    X, y = model.parse_batch(batch)
                if self.fp16_run:
                    with autocast():
                        y_pred = model(X)
                        (
                            mel_loss,
                            gate_loss,
                            mel_loss_batch,
                            gate_loss_batch,
                        ) = criterion(y_pred, y)
                        loss = mel_loss + gate_loss
                        loss_batch = mel_loss_batch + gate_loss_batch
                else:
                    y_pred = model(X)
                    mel_loss, gate_loss, mel_loss_batch, gate_loss_batch = criterion(
                        y_pred, y
                    )
                    loss = mel_loss + gate_loss
                    loss_batch = mel_loss_batch + gate_loss_batch

                if self.distributed_run:
                    reduced_mel_loss = reduce_tensor(mel_loss, self.world_size).item()
                    reduced_gate_loss = reduce_tensor(gate_loss, self.world_size).item()
                    reduced_loss = reduce_mel_loss + reduced_gate_loss
                else:
                    reduced_mel_loss = mel_loss.item()
                    reduced_gate_loss = gate_loss.item()
                    reduced_gate_loss_batch = gate_loss_batch.detach()
                    reduced_mel_loss_batch = mel_loss_batch.detach()

                reduced_loss = reduced_mel_loss + reduced_gate_loss
                reduced_loss_batch = reduced_gate_loss_batch + reduced_mel_loss_batch
                if self.fp16_run:
                    scaler.scale(loss).backward()
                    scaler.unscale_(optimizer)
                    grad_norm = torch.nn.utils.clip_grad_norm(
                        model.parameters(), self.grad_clip_thresh
                    )
                    scaler.step(optimizer)
                    scaler.update()
                else:
                    loss.backward()
                    grad_norm = torch.nn.utils.clip_grad_norm(
                        model.parameters(), self.grad_clip_thresh
                    )
                    optimizer.step()
                step_duration_seconds = time.perf_counter() - start_time
                self.log_training(
                    model,
                    X,
                    y_pred,
                    y,
                    reduced_loss,
                    reduced_mel_loss,
                    reduced_gate_loss,
                    reduced_mel_loss_batch,
                    reduced_gate_loss_batch,
                    grad_norm,
                    step_duration_seconds,
                )
            if epoch % self.epochs_per_checkpoint == 0:
                self.save_checkpoint(
                    f"mellotron_{epoch}",
                    model=model,
                    optimizer=optimizer,
                    iteration=epoch,
                    learning_rate=self.learning_rate,
                    global_step=self.global_step,
                )

            # There's no need to validate in debug mode since we're not really training.
            if self.debug:
                continue
            self.validate(
                model=model,
                val_set=val_set,
                collate_fn=collate_fn,
                criterion=criterion,
            )