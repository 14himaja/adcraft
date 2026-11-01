import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import React, { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { HashtagSelector, normalizeTagInput } from './HashtagSelector';
import * as api from '../lib/api';

vi.mock('../lib/api', async () => {
  const actual = await vi.importActual('../lib/api');
  return {
    ...actual,
    addCustomHashtag: vi.fn(),
    deleteCustomHashtag: vi.fn(),
    recommendHashtags: vi.fn(),
  };
});

function StatefulHashtagSelector(props: Partial<React.ComponentProps<typeof HashtagSelector>>) {
  const [selected, setSelected] = useState<string[]>(props.selectedHashtags ?? []);

  return (
    <HashtagSelector
      {...props}
      selectedHashtags={selected}
      onChange={(tags) => {
        setSelected(tags);
        props.onChange?.(tags);
      }}
    />
  );
}

describe('normalizeTagInput helper', () => {
  it('normalizes tags with and without #', () => {
    expect(normalizeTagInput('SmallBusiness')).toEqual({ tag: '#SmallBusiness', error: null });
    expect(normalizeTagInput('#Trending')).toEqual({ tag: '#Trending', error: null });
    expect(normalizeTagInput('My_Brand2026')).toEqual({ tag: '#My_Brand2026', error: null });
  });

  it('rejects empty input or single hash', () => {
    expect(normalizeTagInput('')).toEqual({ tag: null, error: 'Please enter a hashtag' });
    expect(normalizeTagInput('   ')).toEqual({ tag: null, error: 'Please enter a hashtag' });
    expect(normalizeTagInput('#')).toEqual({ tag: null, error: 'Please enter a hashtag name' });
  });

  it('rejects spaces and unsupported characters', () => {
    expect(normalizeTagInput('Hashtag With Spaces')).toEqual({
      tag: null,
      error: 'Hashtags cannot contain spaces',
    });
    expect(normalizeTagInput('#Brand-Name!')).toEqual({
      tag: null,
      error: 'Hashtags can only contain letters, numbers, and underscores',
    });
  });

  it('rejects overly long hashtags', () => {
    expect(normalizeTagInput('A'.repeat(55))).toEqual({
      tag: null,
      error: 'Hashtag cannot exceed 50 characters',
    });
  });
});

describe('HashtagSelector Component with AI Recommended & Explore Groups', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders section title, live counter, AI Recommended and Explore groups', () => {
    render(
      <HashtagSelector
        selectedHashtags={['#Trending']}
        aiRecommendedHashtags={['#BurgerLovers', '#FoodDelivery', '#Foodie']}
        onChange={vi.fn()}
      />
    );

    expect(screen.getByRole('heading', { level: 3, name: 'Hashtags' })).toBeInTheDocument();
    expect(screen.getByText('1/5 selected')).toBeInTheDocument();
    expect(screen.getByText('AI Recommended')).toBeInTheDocument();
    expect(screen.getByText('Explore Hashtags')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '#BurgerLovers' })).toBeInTheDocument();
  });

  it('selects and deselects AI recommended hashtags', () => {
    const onChange = vi.fn();
    render(
      <StatefulHashtagSelector
        selectedHashtags={[]}
        aiRecommendedHashtags={['#BurgerLovers', '#FoodDelivery', '#Foodie']}
        onChange={onChange}
      />
    );

    const chip = screen.getByRole('button', { name: '#BurgerLovers' });
    fireEvent.click(chip);
    expect(onChange).toHaveBeenLastCalledWith(['#BurgerLovers']);
    expect(screen.getByText('1/5 selected')).toBeInTheDocument();

    // Deselect
    fireEvent.click(chip);
    expect(onChange).toHaveBeenLastCalledWith([]);
    expect(screen.getByText('0/5 selected')).toBeInTheDocument();
  });

  it('allows clicking Refresh AI to request fresh recommendations', async () => {
    vi.mocked(api.recommendHashtags).mockResolvedValue({
      ai_recommended: ['#FreshBurger', '#BurgerTime', '#CrispyFries', '#Foodie', '#FoodLovers'],
      max_limit: 5,
    });

    render(
      <HashtagSelector
        selectedHashtags={[]}
        aiRecommendedHashtags={['#InitialBurgerTag']}
        headline="Gourmet Burger"
        onChange={vi.fn()}
      />
    );

    const refreshBtn = screen.getByRole('button', { name: 'Refresh AI recommendations' });
    fireEvent.click(refreshBtn);

    await waitFor(() => {
      expect(api.recommendHashtags).toHaveBeenCalledWith(
        expect.objectContaining({ headline: 'Gourmet Burger' })
      );
    });
  });

  it('selects predefined hashtags from Explore group', () => {
    const onChange = vi.fn();
    render(
      <StatefulHashtagSelector
        selectedHashtags={[]}
        aiRecommendedHashtags={['#DistinctAiTag1', '#DistinctAiTag2']}
        onChange={onChange}
      />
    );

    const exploreGroup = screen.getByRole('group', { name: 'Predefined Hashtags' });
    const chip = within(exploreGroup).getByRole('button', { name: '#BestDeals' });
    fireEvent.click(chip);
    expect(onChange).toHaveBeenLastCalledWith(['#BestDeals']);
    expect(screen.getByText('1/5 selected')).toBeInTheDocument();
  });

  it('enforces 5-hashtag maximum across AI, explore, and custom groups', () => {
    const onChange = vi.fn();
    const initialFive = ['#FYP', '#ForYou', '#Trending', '#Viral', '#SmallBusiness'];
    render(
      <StatefulHashtagSelector
        selectedHashtags={initialFive}
        aiRecommendedHashtags={['#BurgerLovers']}
        onChange={onChange}
      />
    );

    expect(screen.getByText('5/5 selected')).toBeInTheDocument();

    // Any other unselected chip should be disabled
    const aiGroup = screen.getByRole('group', { name: 'AI Recommended Hashtags' });
    const sixthChip = within(aiGroup).getByRole('button', { name: '#BurgerLovers' });
    expect(sixthChip).toBeDisabled();
    fireEvent.click(sixthChip);
    expect(onChange).not.toHaveBeenCalled();

    // Deselect one to make room
    const exploreGroup = screen.getByRole('group', { name: 'Predefined Hashtags' });
    const fypChip = within(exploreGroup).getByRole('button', { name: '#FYP' });
    fireEvent.click(fypChip);
    expect(onChange).toHaveBeenLastCalledWith(['#ForYou', '#Trending', '#Viral', '#SmallBusiness']);
    expect(screen.getByText('4/5 selected')).toBeInTheDocument();
  });

  it('adds custom hashtag with or without # and auto-selects if slots available', async () => {
    const onChange = vi.fn();
    vi.mocked(api.addCustomHashtag).mockResolvedValueOnce({
      hashtag: '#MyCustomTag',
      custom: ['#MyCustomTag'],
    });

    render(<StatefulHashtagSelector selectedHashtags={['#Trending']} onChange={onChange} />);

    const input = screen.getByPlaceholderText('e.g. MyBrand2026');
    const addButton = screen.getByRole('button', { name: 'Add Hashtag' });

    // Type without '#'
    fireEvent.change(input, { target: { value: 'MyCustomTag' } });
    fireEvent.click(addButton);

    await waitFor(() => {
      expect(api.addCustomHashtag).toHaveBeenCalledWith('#MyCustomTag');
      expect(onChange).toHaveBeenLastCalledWith(['#Trending', '#MyCustomTag']);
    });
  });

  it('rejects duplicate custom hashtag (case-insensitive)', async () => {
    render(<StatefulHashtagSelector selectedHashtags={['#Trending']} onChange={vi.fn()} />);

    const input = screen.getByPlaceholderText('e.g. MyBrand2026');
    const addButton = screen.getByRole('button', { name: 'Add Hashtag' });

    fireEvent.change(input, { target: { value: 'trending' } });
    fireEvent.click(addButton);

    expect(screen.getByText('Hashtag #trending is already selected')).toBeInTheDocument();
    expect(api.addCustomHashtag).not.toHaveBeenCalled();
  });

  it('rejects invalid custom hashtag with clear error', () => {
    render(<StatefulHashtagSelector selectedHashtags={[]} onChange={vi.fn()} />);

    const input = screen.getByPlaceholderText('e.g. MyBrand2026');
    const addButton = screen.getByRole('button', { name: 'Add Hashtag' });

    fireEvent.change(input, { target: { value: 'invalid hashtag with spaces' } });
    fireEvent.click(addButton);

    expect(screen.getByText('Hashtags cannot contain spaces')).toBeInTheDocument();
    expect(api.addCustomHashtag).not.toHaveBeenCalled();
  });

  it('filters explore hashtags by search query and category tabs', () => {
    render(<HashtagSelector selectedHashtags={[]} onChange={vi.fn()} />);

    const searchInput = screen.getByPlaceholderText(/Search library/);
    fireEvent.change(searchInput, { target: { value: 'Foodie' } });

    expect(screen.getByRole('button', { name: '#Foodie' })).toBeInTheDocument();

    // Clear search
    fireEvent.change(searchInput, { target: { value: '' } });

    // Switch to Food & Restaurants tab
    const foodTab = screen.getByRole('tab', { name: 'Food & Restaurants' });
    fireEvent.click(foodTab);

    expect(screen.getByRole('button', { name: '#FoodLovers' })).toBeInTheDocument();
  });

  it('displays selected hashtags preview with clear badges and remove button', () => {
    const onChange = vi.fn();
    render(
      <StatefulHashtagSelector
        selectedHashtags={['#BurgerLovers', '#ShopNow']}
        aiRecommendedHashtags={['#BurgerLovers']}
        onChange={onChange}
      />
    );

    expect(screen.getByText('Selected hashtags preview')).toBeInTheDocument();
    expect(screen.getByText('2 of 5 chosen')).toBeInTheDocument();

    // Origin badges
    expect(screen.getByText('AI')).toBeInTheDocument();
    expect(screen.getByText('Library')).toBeInTheDocument();

    const removeBtn = screen.getByRole('button', { name: 'Remove #BurgerLovers' });
    fireEvent.click(removeBtn);

    expect(onChange).toHaveBeenLastCalledWith(['#ShopNow']);
    expect(screen.getByText('1 of 5 chosen')).toBeInTheDocument();
  });

  it('displays publishing destination compatibility notice', () => {
    render(<HashtagSelector selectedHashtags={[]} onChange={vi.fn()} showDestinationNotice={true} />);

    expect(screen.getByText('Publishing Compatibility')).toBeInTheDocument();
    expect(screen.getByText(/Instagram Feed/)).toBeInTheDocument();
  });
  it('renders Regenerate Suggestions button and label showing generation for current ad', () => {
    render(<HashtagSelector selectedHashtags={[]} onChange={vi.fn()} />);

    expect(screen.getByText('Generated for this ad')).toBeInTheDocument();
    expect(screen.getByText('Regenerate Suggestions')).toBeInTheDocument();
  });

  it('displays reason when expanding an AI hashtag explanation', async () => {
    vi.mocked(api.recommendHashtags).mockResolvedValueOnce({
      ai_recommended: ['#FreshBurger'],
      recommended_hashtags: [
        { tag: '#FreshBurger', reason: 'Directly relevant to the advertised gourmet burger' },
      ],
      alternative_hashtags: ['#LocalEats'],
      max_limit: 5,
    });

    render(
      <HashtagSelector
        selectedHashtags={[]}
        contextText="Gourmet fresh burger promotion"
        onChange={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByRole('button', { name: '#FreshBurger' })).toBeInTheDocument();
    });

    // Info toggle button
    const infoBtn = screen.getByRole('button', { name: 'Why #FreshBurger?' });
    expect(infoBtn).toBeInTheDocument();
    fireEvent.click(infoBtn);

    expect(screen.getByText(/Directly relevant to the advertised gourmet burger/)).toBeInTheDocument();
  });

  it('renders alternative suggestions and allows selecting them up to limit', async () => {
    const onChange = vi.fn();
    vi.mocked(api.recommendHashtags).mockResolvedValueOnce({
      ai_recommended: ['#FreshBurger'],
      recommended_hashtags: [{ tag: '#FreshBurger', reason: 'Burger tag' }],
      alternative_hashtags: ['#LocalEats', '#FoodLovers'],
      max_limit: 5,
    });

    render(
      <StatefulHashtagSelector
        selectedHashtags={[]}
        contextText="Gourmet fresh burger promotion"
        onChange={onChange}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('Alternative Suggestions')).toBeInTheDocument();
    });

    const altChip = screen.getByRole('button', { name: '#LocalEats' });
    fireEvent.click(altChip);
    expect(onChange).toHaveBeenLastCalledWith(['#LocalEats']);
  });
});
