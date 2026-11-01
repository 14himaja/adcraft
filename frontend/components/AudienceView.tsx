'use client';

import React, { useState, useEffect } from 'react';
import {
  Search,
  Plus,
  X,
  MapPin,
  Calendar,
  Sparkles,
  ShieldCheck,
  ArrowRight,
} from 'lucide-react';
import { searchInterests, MetaInterest, searchLocations, MetaLocation } from '../lib/api';

const COUNTRIES: [string, string][] = [
  ['IN', 'India'],
  ['US', 'United States'],
  ['GB', 'United Kingdom'],
  ['CA', 'Canada'],
  ['AE', 'United Arab Emirates'],
  ['SG', 'Singapore'],
];
const MAX_CITIES = 10;
const MAX_INTERESTS = 5;

interface AudienceViewProps {
  onApplyToCampaign?: (audience: {
    country: string;
    cities: MetaLocation[];
    age_min: number;
    age_max: number;
    gender: 'ALL' | 'MEN' | 'WOMEN';
    interests: MetaInterest[];
  }) => void;
}

export function AudienceView({ onApplyToCampaign }: AudienceViewProps) {
  const [country, setCountry] = useState('IN');
  const [selectedCities, setSelectedCities] = useState<MetaLocation[]>([]);
  const [cityResults, setCityResults] = useState<MetaLocation[]>([]);
  const [cityInput, setCityInput] = useState('');
  const [ageMin, setAgeMin] = useState(18);
  const [ageMax, setAgeMax] = useState(65);
  const [gender, setGender] = useState<'ALL' | 'MEN' | 'WOMEN'>('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<MetaInterest[]>([]);
  const [selectedInterests, setSelectedInterests] = useState<MetaInterest[]>([]);
  const [loadingInterests, setLoadingInterests] = useState(false);
  const visibleResults = searchQuery.trim() ? searchResults : [];

  // Presets trigger a real Meta lookup; only returned Meta interest IDs can be selected.
  const presetInterests = [
    'Software engineering',
    'Artificial intelligence',
    'Digital marketing',
    'Web development',
    'E-commerce',
    'Entrepreneurship',
    'Graphic design',
    'Data science',
  ];

  useEffect(() => {
    if (!searchQuery.trim()) return;
    const timer = setTimeout(async () => {
      setLoadingInterests(true);
      try {
        const results = await searchInterests(searchQuery);
        setSearchResults(results);
      } catch {
        setSearchResults([]);
      } finally {
        setLoadingInterests(false);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (!cityInput.trim()) {
        setCityResults([]);
        return;
      }
      searchLocations(cityInput.trim(), country).then(setCityResults).catch(() => setCityResults([]));
    }, 300);
    return () => clearTimeout(timer);
  }, [cityInput, country]);

  const handleAddCity = (city: MetaLocation) => {
    if (selectedCities.length < MAX_CITIES && !selectedCities.some((selected) => selected.key === city.key)) {
      setSelectedCities([...selectedCities, city]);
    }
    setCityInput('');
    setCityResults([]);
  };

  const handleRemoveCity = (cityKey: string) => {
    setSelectedCities(selectedCities.filter((city) => city.key !== cityKey));
  };

  const handleToggleInterest = (interest: MetaInterest) => {
    if (selectedInterests.some((selected) => selected.id === interest.id)) {
      setSelectedInterests(selectedInterests.filter((selected) => selected.id !== interest.id));
    } else {
      setSelectedInterests([...selectedInterests, interest]);
    }
  };

  const handleUseInCampaign = () => {
    if (onApplyToCampaign) {
      onApplyToCampaign({
        country,
        cities: selectedCities,
        age_min: ageMin,
        age_max: ageMax,
        gender,
        interests: selectedInterests,
      });
    }
  };

  const countryName = COUNTRIES.find(([code]) => code === country)?.[1] ?? country;

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 py-6 border-b border-[#EDE6DD] dark:border-white/10">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-xl font-extrabold text-[#1F1A18] dark:text-white tracking-tight">
              Audience Intelligence & Targeting
            </h2>
            <span className="text-[11px] font-bold px-2.5 py-0.5 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-700 dark:text-emerald-400">
              Meta Graph v26.0
            </span>
          </div>
          <p className="text-xs text-[#7A6C63] dark:text-slate-400 mt-1 max-w-xl">
            Configure precision demographic, geographic, and interest-based targeting connected to your Meta ad account.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleUseInCampaign}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-[#F26D5B] hover:bg-[#E05C4A] text-white text-xs font-bold transition-all shadow-md shadow-[#F26D5B]/20 cursor-pointer hover:scale-105 active:scale-95"
          >
            <span>Apply to New Campaign</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Main Grid: Left Controls (8 cols), Right Reach Card (4 cols) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Targeting Controls */}
        <div className="lg:col-span-8 space-y-6">
          {/* 1. Location & Geography */}
          <div className="py-6 border-b border-[#EDE6DD] dark:border-white/10 space-y-4">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-xl bg-[#FEECE7] dark:bg-[#F26D5B]/15 text-[#F26D5B] flex items-center justify-center">
                <MapPin className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-[#1F1A18] dark:text-white">
                  Geographic Targeting
                </h3>
                <p className="text-xs text-[#7A6C63] dark:text-slate-400">
                  Choose a country, then select matching locations returned by Meta.
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label htmlFor="audience-country" className="block text-xs font-bold text-[#5C5047] dark:text-slate-300 mb-1.5">
                  Target Country
                </label>
                <select
                  id="audience-country"
                  value={country}
                  onChange={(e) => {
                    setCountry(e.target.value);
                    setSelectedCities([]);
                    setCityInput('');
                    setCityResults([]);
                  }}
                  className="w-full px-3.5 py-2.5 bg-[#FAF8F5] dark:bg-[#0F172A] border border-[#EDE6DD] dark:border-white/10 rounded-xl text-xs sm:text-sm font-semibold text-[#1F1A18] dark:text-white focus:outline-none focus:ring-2 focus:ring-[#F26D5B]/30"
                >
                  {COUNTRIES.map(([code, name]) => (
                    <option key={code} value={code}>{name} ({code})</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-bold text-[#5C5047] dark:text-slate-300 mb-1.5">
                  Add Target City
                </label>
                <div className="relative">
                  <input
                    type="text"
                    value={cityInput}
                    onChange={(e) => setCityInput(e.target.value)}
                    placeholder="Search a Meta city, e.g. Pune"
                    className="w-full px-3.5 py-2.5 bg-[#FAF8F5] dark:bg-[#0F172A] border border-[#EDE6DD] dark:border-white/10 rounded-xl text-xs sm:text-sm text-[#1F1A18] dark:text-white placeholder-[#9C8F85] focus:outline-none focus:ring-2 focus:ring-[#F26D5B]/30"
                  />
                  {cityResults.length > 0 && selectedCities.length < MAX_CITIES && (
                    <div className="absolute z-20 top-full mt-1 w-full p-1 bg-white dark:bg-[#0F172A] rounded-xl border border-[#EDE6DD] dark:border-white/10 shadow-lg">
                      {cityResults.map((city) => (
                        <button key={city.key} type="button" onClick={() => handleAddCity(city)} className="w-full text-left px-3 py-2 rounded-lg text-xs hover:bg-[#FEECE7] dark:hover:bg-white/5">
                          {city.name} <span className="text-[#9C8F85]">({city.country_code})</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* City Tags */}
            <div className="flex flex-wrap gap-2 pt-1">
              {selectedCities.map((c) => (
                <span
                  key={c.key}
                  className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#FAF8F5] dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10 text-xs font-semibold text-[#1F1A18] dark:text-slate-200"
                >
                  <MapPin className="w-3 h-3 text-[#F26D5B]" />
                  <span>{c.name}</span>
                  <button
                    type="button"
                    onClick={() => handleRemoveCity(c.key)}
                    className="hover:text-rose-500 cursor-pointer ml-0.5"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
          </div>

          {/* 2. Demographics (Age & Gender) */}
          <div className="py-6 border-b border-[#EDE6DD] dark:border-white/10 space-y-4">
            <div className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-xl bg-purple-500/10 text-purple-600 dark:text-purple-400 flex items-center justify-center">
                <Calendar className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-[#1F1A18] dark:text-white">
                  Age & Gender Demographics
                </h3>
                <p className="text-xs text-[#7A6C63] dark:text-slate-400">
                  Target exact buyer profile and student / professional brackets
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-bold text-[#5C5047] dark:text-slate-300 mb-1.5">
                  Min Age: {ageMin}
                </label>
                <input
                  type="range"
                  min="18"
                  max="60"
                  value={ageMin}
                  onChange={(e) => setAgeMin(Number(e.target.value))}
                  className="w-full accent-[#F26D5B] cursor-pointer"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-[#5C5047] dark:text-slate-300 mb-1.5">
                  Max Age: {ageMax}+
                </label>
                <input
                  type="range"
                  min="20"
                  max="65"
                  value={ageMax}
                  onChange={(e) => setAgeMax(Number(e.target.value))}
                  className="w-full accent-[#F26D5B] cursor-pointer"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-[#5C5047] dark:text-slate-300 mb-1.5">
                  Gender
                </label>
                <div className="flex gap-1 bg-[#FAF8F5] dark:bg-[#0F172A] p-1 rounded-xl border border-[#EDE6DD] dark:border-white/10">
                  {(['ALL', 'MEN', 'WOMEN'] as const).map((g) => (
                    <button
                      key={g}
                      type="button"
                      onClick={() => setGender(g)}
                      className={`flex-1 py-1 rounded-lg text-xs font-bold transition-all cursor-pointer ${
                        gender === g
                          ? 'bg-white dark:bg-[#1E293B] text-[#F26D5B] shadow-2xs'
                          : 'text-[#7A6C63] dark:text-slate-400'
                      }`}
                    >
                      {g === 'ALL' ? 'All' : g === 'MEN' ? 'Men' : 'Women'}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* 3. Real Meta Graph Interests Search & Selector */}
          <div className="py-6 border-b border-[#EDE6DD] dark:border-white/10 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-400 flex items-center justify-center">
                  <Sparkles className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-[#1F1A18] dark:text-white">
                    Meta Detailed Interests
                  </h3>
                  <p className="text-xs text-[#7A6C63] dark:text-slate-400">
                    Live interest lookup from Meta Marketing API v26.0
                  </p>
                </div>
              </div>

              <span className="text-xs font-bold text-[#F26D5B]">
                {selectedInterests.length} selected
              </span>
            </div>

            {/* Search Input */}
            <div className="relative">
              <Search className="w-4 h-4 text-[#9C8F85] absolute left-3.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search Meta interests (e.g. Python, AI, Marketing, Coding)..."
                className="w-full pl-10 pr-4 py-2.5 bg-[#FAF8F5] dark:bg-[#0F172A] border border-[#EDE6DD] dark:border-white/10 rounded-xl text-xs sm:text-sm text-[#1F1A18] dark:text-white placeholder-[#9C8F85] focus:outline-none focus:ring-2 focus:ring-[#F26D5B]/30"
              />
              {loadingInterests && (
                <div className="absolute right-3.5 top-1/2 -translate-y-1/2 w-4 h-4 border-2 border-[#F26D5B] border-t-transparent rounded-full animate-spin" />
              )}
            </div>

            {/* Live Search Results Dropdown */}
            {visibleResults.length > 0 && (
              <div className="py-3 border-b border-[#EDE6DD] dark:border-white/10 space-y-1.5">
                <p className="text-[10px] font-bold uppercase text-[#8C7E74] dark:text-slate-400 px-1">
                  Meta Search Matches:
                </p>
                <div className="flex flex-wrap gap-2">
                  {visibleResults.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => handleToggleInterest(item)}
                      disabled={selectedInterests.length >= MAX_INTERESTS && !selectedInterests.some((selected) => selected.id === item.id)}
                      title={selectedInterests.length >= MAX_INTERESTS ? `Select up to ${MAX_INTERESTS} interests` : undefined}
                      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold transition-all cursor-pointer ${
                        selectedInterests.some((selected) => selected.id === item.id)
                          ? 'bg-[#F26D5B] text-white shadow-xs'
                          : 'bg-white dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10 text-[#1F1A18] dark:text-white hover:border-[#F26D5B]'
                      }`}
                    >
                      <Plus className="w-3 h-3" />
                      <span>{item.name}</span>
                      <span className="text-[10px] opacity-75">
                        ({(item.audience_size_lower / 1000000).toFixed(1)}M)
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {selectedInterests.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {selectedInterests.map((interest) => (
                  <span key={interest.id} className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#FEECE7] dark:bg-[#F26D5B]/20 text-[#F26D5B] border border-[#FAD6CD] dark:border-[#F26D5B]/30 text-xs font-semibold">
                    {interest.name}
                    <button type="button" aria-label={`Remove interest ${interest.name}`} onClick={() => handleToggleInterest(interest)} className="hover:text-rose-600">
                      <X className="w-3 h-3" />
                    </button>
                  </span>
                ))}
              </div>
            )}

            {/* Quick Presets */}
            <div>
              <p className="text-[11px] font-bold text-[#8C7E74] dark:text-slate-400 mb-2">
                Search a preset in Meta to choose a supported interest:
              </p>
              <div className="flex flex-wrap gap-2">
                {presetInterests.map((interest) => (
                  <button
                    key={interest}
                    type="button"
                    onClick={() => setSearchQuery(interest)}
                    className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold transition-all cursor-pointer bg-[#FAF8F5] dark:bg-white/5 border border-[#EDE6DD] dark:border-white/10 text-[#5C5047] dark:text-slate-300 hover:border-[#F26D5B]"
                  >
                    <span>{interest}</span>
                    <Search className="w-3 h-3 text-[#9C8F85]" />
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Right Reach Estimator Card */}
        <div className="lg:col-span-4 space-y-6">
          <div className="py-6 border-b border-[#EDE6DD] dark:border-white/10 space-y-5 sticky top-20">
            <div className="flex items-center justify-between pb-4 border-b border-[#EDE6DD]/70 dark:border-white/10">
              <h4 className="text-sm font-bold text-[#1F1A18] dark:text-white">
                Audience Summary
              </h4>
            </div>
            <p className="text-xs text-[#7A6C63] dark:text-slate-400">
              Meta reports the real reach once a campaign with this audience is published.
            </p>

            {/* Breakdown meters */}
            <div className="space-y-3 pt-2 text-xs">

              <div className="py-3 border-b border-[#EDE6DD] dark:border-white/5 space-y-2">
                <div className="flex items-center justify-between text-[#7A6C63] dark:text-slate-400">
                  <span>Location</span>
                  <span className="font-bold text-[#1F1A18] dark:text-white">{countryName} ({selectedCities.length} cities)</span>
                </div>
                <div className="flex items-center justify-between text-[#7A6C63] dark:text-slate-400">
                  <span>Demographics</span>
                  <span className="font-bold text-[#1F1A18] dark:text-white">{ageMin}–{ageMax} yrs, {gender}</span>
                </div>
                <div className="flex items-center justify-between text-[#7A6C63] dark:text-slate-400">
                  <span>Meta Interests</span>
                  <span className="font-bold text-[#1F1A18] dark:text-white">{selectedInterests.length} selected</span>
                </div>
              </div>
            </div>

            {/* Zero Spend Notice */}
            <div className="p-3 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-800 dark:text-emerald-300 flex items-start gap-2.5 text-xs">
              <ShieldCheck className="w-4 h-4 shrink-0 mt-0.5 text-emerald-600 dark:text-emerald-400" />
              <span>
                Audience research does not deliver ads. Publishing starts delivery and charges the connected ad account under the campaign budget.
              </span>
            </div>

            <button
              type="button"
              onClick={handleUseInCampaign}
              className="w-full py-3 rounded-xl bg-[#F26D5B] hover:bg-[#E05C4A] text-white text-xs font-bold transition-all shadow-md shadow-[#F26D5B]/25 flex items-center justify-center gap-2 cursor-pointer hover:scale-102 active:scale-98"
            >
              <span>Build Campaign With This Audience</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default AudienceView;
