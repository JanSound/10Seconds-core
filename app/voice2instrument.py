import librosa
import pretty_midi
import numpy as np
import copy
from fastapi import HTTPException


def find_silence_index(y):
    non_silence_indices = librosa.effects.split(y, top_db=20)
    silence_index = []
    if len(non_silence_indices):
        silence_index.append(np.array([0, non_silence_indices[0][0]]))

    for i in range(len(non_silence_indices) - 1):
        silence_index.append(np.array([non_silence_indices[i][1], non_silence_indices[i + 1][0]]))

    # 무음인 부분 인덱스 생성
    silence_index.append(np.array([non_silence_indices[len(non_silence_indices) - 1][1], y.shape[0]]))
    return silence_index


def voice2midi(y):
    # 무음인 부분 진폭 0으로 수정
    y2 = copy.deepcopy(y)
    silence_index = find_silence_index(y2)
    for silence in silence_index:
        y[silence[0]:silence[1]] = 0

    # 기본 주파수 찾기
    f0, voiced_flag, voiced_probs = librosa.pyin(y, fmin=librosa.note_to_hz('C2'), fmax=librosa.note_to_hz('C7'))
    # velocity 적용
    rms = librosa.feature.rms(y=y)

    # 주파수와 해당 주파수의 시간대 찾기
    f0_times = librosa.times_like(f0)

    f0_group = []
    f0_time = []
    start_f = 0
    f_temp = []
    t_temp = []
    half_tone = 0
    change = 1

    for f, t in zip(f0, f0_times):
        # 만약 주파수가 0보다 크다면
        if f > 0:
            # 만약 평균율에 의해 group이 새로 시작해야 한다면
            if change:
                start_f = f
                half_tone = start_f*(1.059463) - start_f
                change = 0
                f_temp = [f]
                t_temp = [t]
                continue
            # 만약 평균율에 의해 음이 바뀌지 않아도 된다면
            if f<=start_f+half_tone or f>start_f-half_tone:
                f_temp.append(f)
                t_temp.append(t)
                continue
            # 만약 평균율에 의해 group이 끝나야 한다면
            if f>start_f+half_tone or f<start_f-half_tone:
                # 새로운 주파수 그룹
                f0_group.append(f_temp)
                f0_time.append(t_temp)
                start_f = f
                half_tone = start_f * (1.059463) - start_f
                f_temp.append(f)
                t_temp.append(t)
                f_temp = [f]
                t_temp = [t]
        # 중간에 0보다 같거나 작은 주파수가 있거나 평균율에 의해 새로운 그룹이 시작되어야 한다면
        else:
            if len(f_temp):
                f0_group.append(f_temp)
                f0_time.append(t_temp)
            f_temp = []
            t_temp = []
            change = 1

    if len(f0_group) == 0:
        raise HTTPException(status_code=400, detail=f"volume of voice is too low to detect frequencies")

    count = 0
    piano_midi = pretty_midi.PrettyMIDI()
    bass_midi = pretty_midi.PrettyMIDI()
    drum_midi = pretty_midi.PrettyMIDI()
    bass_drum = 35
    acoustic_snare = 38
    closed_hi_hat = 42
    # piano
    piano_program = pretty_midi.instrument_name_to_program('Acoustic Grand Piano')
    piano = pretty_midi.Instrument(piano_program, name='piano')
    # bass
    bass = pretty_midi.Instrument(0, name='bass')
    # drum
    drum = pretty_midi.Instrument(0, is_drum=True, name='drum')

    # drum MIDI 데이터
    for i in range(len(f0_group)):
        if len(f0_group[i]):
            start = f0_time[i][0]
            end = f0_time[i][-1]
            # velocity = int(rms[0][librosa.time_to_frames(start)]/ np.max(rms[0]) * 127)
            velocity = 100
            if count % 4 == 0:
                note = pretty_midi.Note(velocity=velocity, start=start, pitch=bass_drum, end=end)
                drum.notes.append(note)
                note = pretty_midi.Note(velocity=velocity, start=start, pitch=closed_hi_hat, end=end)
                drum.notes.append(note)
                count += 1

            elif count % 4 == 1:
                note = pretty_midi.Note(velocity=velocity, start=start, pitch=closed_hi_hat, end=end)
                drum.notes.append(note)
                count += 1

            elif count % 4 == 2:
                note = pretty_midi.Note(velocity=velocity, start=start, pitch=bass_drum, end=end)
                drum.notes.append(note)
                note = pretty_midi.Note(velocity=velocity, start=start, pitch=closed_hi_hat, end=end)
                drum.notes.append(note)
                note = pretty_midi.Note(velocity=velocity, start=start, pitch=acoustic_snare, end=end)
                drum.notes.append(note)
                count += 1

            elif count % 4 == 3:
                note = pretty_midi.Note(velocity=velocity, start=start, pitch=closed_hi_hat, end=end)
                drum.notes.append(note)
                count += 1

    # piano 또는 bass MIDI 데이터
    for i in range(len(f0_group)):
        if len(f0_group[i]):
            mean_pitch = np.mean(f0_group[i])

            pitch = int(round(librosa.hz_to_midi(mean_pitch)))

            start = f0_time[i][0]
            end = f0_time[i][-1]

            # velocity = int(rms[0][librosa.time_to_frames(start)]/ np.max(rms[0]) * 127)
            velocity = 100
            note = pretty_midi.Note(velocity=velocity, pitch=pitch, start=start, end=end)
            piano.notes.append(note)
            bass.notes.append(note)

    piano_midi.instruments.append(piano)
    bass_midi.instruments.append(bass)
    drum_midi.instruments.append(drum)

    return {"piano": piano_midi, "bass": bass_midi, "drum": drum_midi}

